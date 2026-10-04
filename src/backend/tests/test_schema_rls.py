import asyncio
from uuid import uuid4

import psycopg
import pytest

from app.db import tenant_transaction


def test_web_has_no_context_and_no_role_escalation(db_fixture):
    async def check():
        async with db_fixture.pool.connection() as conn:
            row = await (await conn.execute('SELECT session_user,current_user')).fetchone()
            assert row == {'session_user': 'ai_web', 'current_user': 'ai_web'}
            assert await (await conn.execute('SELECT * FROM portal.conversations')).fetchall() == []
            row = await (await conn.execute(
                'SELECT rolsuper,rolbypassrls,rolinherit,rolcreatedb,rolcreaterole '
                'FROM pg_roles WHERE rolname=session_user')).fetchone()
            assert not any(row.values())
            for role in ('ai_owner', 'ai_policy_executor', 'ai_index', 'ai_meter'):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    await conn.execute(f'SET ROLE {role}')
    db_fixture.run(check())


@pytest.mark.parametrize('actor,tenant,expected', [
    ('A-U1', 'A', 1), ('A-U2', 'A', 1), ('B-U1', 'B', 1),
    ('A-ADM', 'A', 0), ('P-A', 'A', 0), ('DUAL', 'A', 1), ('DUAL', 'B', 1),
])
def test_owner_isolation_without_tenant_where(db_fixture, actor, tenant, expected):
    async def check():
        ctx = await db_fixture.context(actor, tenant)
        async with tenant_transaction(db_fixture.pool, ctx) as conn:
            rows = await (await conn.execute('SELECT * FROM portal.conversations')).fetchall()
            assert len(rows) == expected
            assert all(r['owner_user_id'] == ctx.user_id and r['tenant_id'] == ctx.tenant_id for r in rows)
            agents = await (await conn.execute('SELECT * FROM portal.agent_configs')).fetchall()
            assert len(agents) == 2 and all(r['tenant_id'] == ctx.tenant_id for r in agents)
    db_fixture.run(check())


@pytest.mark.parametrize('setting', ['app.user_id', 'app.tenant_id', 'app.session_id'])
@pytest.mark.parametrize('value', ['', 'malformed'])
def test_bad_context_denies(db_fixture, setting, value):
    async def check():
        ctx = await db_fixture.context('A-U1', 'A')
        async with tenant_transaction(db_fixture.pool, ctx) as conn:
            await conn.execute('SELECT set_config(%s,%s,true)', (setting, value))
            assert await (await conn.execute('SELECT * FROM portal.conversations')).fetchall() == []
    db_fixture.run(check())


def test_write_policy_and_immutable_binding(db_fixture):
    async def check():
        ctx = await db_fixture.context('A-U1', 'A')
        for tenant, owner in [('B', 'A-U1'), ('A', 'A-U2')]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                async with tenant_transaction(db_fixture.pool, ctx) as conn:
                    await conn.execute('INSERT INTO portal.conversations '
                        '(tenant_id,conversation_id,owner_user_id,agent_key) VALUES (%s,%s,%s,%s)',
                        (db_fixture.tenant_ids[tenant], uuid4(), db_fixture.actor_ids[owner], 'general'))
        for column in ('tenant_id', 'owner_user_id', 'agent_key'):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                async with tenant_transaction(db_fixture.pool, ctx) as conn:
                    await conn.execute(f'UPDATE portal.conversations SET {column}={column}')
        async with tenant_transaction(db_fixture.pool, ctx) as conn:
            assert (await conn.execute('UPDATE portal.conversations SET updated_at=clock_timestamp()')).rowcount == 1
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            async with tenant_transaction(db_fixture.pool, ctx) as conn:
                await conn.execute('INSERT INTO portal.conversations '
                    '(tenant_id,conversation_id,owner_user_id,agent_key) VALUES (%s,%s,%s,%s)',
                    (ctx.tenant_id, uuid4(), ctx.user_id, 'unknown_agent'))
    db_fixture.run(check())


@pytest.mark.parametrize('mutation', ['account', 'tenant', 'membership', 'revision', 'revoked', 'expired', 'idle'])
def test_current_state_revocation_in_same_transaction(db_fixture, mutation):
    async def check():
        ctx = await db_fixture.context('A-U1', 'A')
        async with tenant_transaction(db_fixture.pool, ctx) as conn:
            assert len(await (await conn.execute('SELECT * FROM portal.conversations')).fetchall()) == 1
            db_fixture.mutate_access(ctx, mutation)
            assert await (await conn.execute('SELECT * FROM portal.conversations')).fetchall() == []
    db_fixture.run(check())


def test_raw_permissions_and_rls_catalog(db_fixture):
    async def check():
        async with db_fixture.pool.connection() as conn:
            for table in ('security.accounts', 'security.sessions', 'security.memberships', 'ops.project_budget'):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    await conn.execute(f'SELECT * FROM {table}')
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                await conn.execute('CREATE TEMP TABLE forbidden(x int)')
    db_fixture.run(check())
    db_fixture.verify_catalog()
    for role in ('ai_index', 'ai_meter'):
        with db_fixture.role_connection(role) as conn:
            for query in ('SELECT * FROM portal.conversations', 'SELECT * FROM security.accounts',
                          'SELECT * FROM ops.project_budget',
                          'SELECT * FROM security.current_membership(NULL,NULL)'):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(query)


@pytest.mark.parametrize('actor,tenant,role,manage', [
    ('A-U1', 'A', 'USER', False), ('A-ADM', 'A', 'TADMIN', True),
    ('P-A', 'A', 'PADMIN', True), ('DUAL-ADM', 'B', 'TADMIN', True),
    ('P_READ_ONLY', 'A', 'PADMIN', False), ('P_WRITE_ONLY', 'A', 'PADMIN', False),
])
def test_current_membership_not_global_tenant_access(db_fixture, actor, tenant, role, manage):
    async def check():
        ctx = await db_fixture.context(actor, tenant)
        async with db_fixture.pool.connection() as conn:
            row = await (await conn.execute('SELECT * FROM security.current_membership(%s,%s)',
                (ctx.session_id, ctx.tenant_id))).fetchone()
            assert row['effective_role'] == role and row['can_manage'] is manage
            if actor == 'P-A':
                assert await (await conn.execute('SELECT * FROM security.current_membership(%s,%s)',
                    (ctx.session_id, db_fixture.tenant_ids['B']))).fetchall() == []
    db_fixture.run(check())


def test_inactive_session_and_no_membership_denied(db_fixture):
    async def check():
        for actor in ('INACTIVE', 'NO_MEMBERS'):
            with pytest.raises(ValueError, match='CONTEXT_UNAVAILABLE'):
                await db_fixture.context(actor, 'A')
    db_fixture.run(check())


def test_no_context_insert_and_allowed_own_insert(db_fixture):
    async def check():
        params=(db_fixture.tenant_ids['A'],uuid4(),db_fixture.actor_ids['A-U1'],'general')
        query='INSERT INTO portal.conversations(tenant_id,conversation_id,owner_user_id,agent_key) VALUES(%s,%s,%s,%s)'
        async with db_fixture.pool.connection() as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege): await conn.execute(query,params)
        ctx=await db_fixture.context('A-U1','A')
        async with tenant_transaction(db_fixture.pool,ctx) as conn:
            assert (await conn.execute(query,params)).rowcount==1
    db_fixture.run(check())


def test_composite_membership_fk_rejects_foreign_owner(db_fixture):
    with db_fixture.db.admin_connection() as conn:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute('INSERT INTO portal.conversations(tenant_id,conversation_id,owner_user_id,agent_key) VALUES(%s,%s,%s,%s)',
                (db_fixture.tenant_ids['A'],uuid4(),db_fixture.actor_ids['B-U1'],'general'))
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute('INSERT INTO security.managed_tenants(tenant_id,user_id) VALUES(%s,%s)',
                (db_fixture.tenant_ids['B'],db_fixture.actor_ids['P-A']))


@pytest.mark.parametrize('actor,tenant,expected',[('A-U1','A',0),('A-ADM','A',1),('B-ADM','B',1),('P-A','A',1)])
def test_audit_reads_only_current_managed_tenant(db_fixture,actor,tenant,expected):
    async def check():
        ctx=await db_fixture.context(actor,tenant)
        async with tenant_transaction(db_fixture.pool,ctx) as conn:
            rows=await (await conn.execute('SELECT * FROM ops.audit_events')).fetchall()
            assert len(rows)==expected
            assert all(r['scope_kind']=='tenant' and r['tenant_id']==ctx.tenant_id for r in rows)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                async with conn.transaction():
                    await conn.execute('INSERT INTO ops.audit_events(event_id,scope_kind,action,result) VALUES(%s,%s,%s,%s)',
                        (uuid4(),'platform','forbidden','ok'))
    db_fixture.run(check())


@pytest.mark.parametrize('target',['platform','managed'])
def test_platform_and_managed_revoke_recompute_privileges(db_fixture,target):
    async def check():
        ctx=await db_fixture.context('P-A','A')
        async with tenant_transaction(db_fixture.pool,ctx) as conn:
            assert (await (await conn.execute('SELECT security.can_manage_current_tenant(%s) AS allowed',(ctx.tenant_id,))).fetchone())['allowed']
            with db_fixture.db.admin_connection() as admin:
                table='security.platform_access' if target=='platform' else 'security.managed_tenants'
                admin.execute(f'UPDATE {table} SET active=false WHERE user_id=%s',(ctx.user_id,))
            row=await (await conn.execute('SELECT * FROM security.current_membership(%s,%s)',(ctx.session_id,ctx.tenant_id))).fetchone()
            assert row['can_manage'] is False
            assert row['effective_role']==('USER' if target=='platform' else 'PADMIN')
            assert not (await (await conn.execute('SELECT security.can_manage_current_tenant(%s) AS allowed',(ctx.tenant_id,))).fetchone())['allowed']
    db_fixture.run(check())
