import asyncio
from dataclasses import FrozenInstanceError
from decimal import Decimal
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb
import pytest
from psycopg_pool import PoolTimeout

from app.ai.pricing import PRICE, reservation_krw, cost_krw
from app.ai.types import DispatchClaim, ProviderOutcome, UsageReceipt
from app.db import DatabaseBoundaryError, make_meter_pool, open_meter_pool, open_web_pool, tenant_transaction


@pytest.fixture
def b_rows(db_fixture):
    f = db_fixture; runs = {}
    with f.db.admin_connection() as conn:
        for key, cid in f.conversation_ids.items():
            tenant, actor = key.split(':'); run = uuid4(); runs[key] = run
            conn.execute("INSERT INTO portal.runs(tenant_id,run_id,conversation_id,owner_user_id,client_send_id,"
                "request_hash,agent_key,config_snapshot,origin_session_id,execution_mode,state,stage,answer_kind,ended_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,'general','{}',%s,'mock','completed','terminal','answer',clock_timestamp())",
                (f.tenant_ids[tenant],run,cid,f.actor_ids[actor],uuid4(),bytes(32),f.state.session_ids[actor]))
            for seq, role, kind in [(1,'user','user'),(2,'assistant','general_assistant')]:
                conn.execute('INSERT INTO portal.messages(tenant_id,message_id,conversation_id,owner_user_id,agent_key,'
                    'sequence_no,role,body,run_id,payload_kind) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (f.tenant_ids[tenant],uuid4(),cid,f.actor_ids[actor],'general',seq,role,'synthetic test message',run,kind))
        for tenant in ['A','B']:
            for budget, in conn.execute('SELECT budget_id FROM ops.project_budget').fetchall():
                conn.execute('INSERT INTO ops.tenant_budgets(tenant_id,budget_id,allocated_cap_krw,local_cap_krw) '
                    'VALUES(%s,%s,12500,12500)',(f.tenant_ids[tenant],budget))
    return runs


def insert_run(f, *, tenant='A', owner='A-U1', conversation=None, session=None, agent='general', mode='mock'):
    run = uuid4()
    with f.db.admin_connection() as conn:
        conn.execute('INSERT INTO portal.runs(tenant_id,run_id,conversation_id,owner_user_id,client_send_id,'
            'request_hash,agent_key,config_snapshot,origin_session_id,execution_mode) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (f.tenant_ids[tenant],run,conversation or f.conversation_ids['A:A-U1'],f.actor_ids[owner],
             uuid4(),bytes(32),agent,Jsonb({}),session or f.state.session_ids[owner],mode))
    return run


def insert_call(f,runs, *, owner='A-U1', tenant='A', budget_mode='mock', call_mode='mock', job_id=None, operation='generate_general'):
    call = uuid4()
    with f.db.admin_connection() as conn:
        budget=conn.execute('SELECT budget_id FROM ops.project_budget WHERE mode=%s',(budget_mode,)).fetchone()[0]
        conn.execute('INSERT INTO ops.call_attempts(tenant_id,call_id,run_id,job_id,initiator_user_id,operation,'
            'budget_id,mode,agent_key,config_revision,step_key,input_fingerprint,permit_revision,permit_expires_at,'
            'reserved_krw,price_snapshot) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,1,clock_timestamp()+interval \'10 seconds\',3.64,%s)',
            (f.tenant_ids[tenant],call,runs['A:A-U1'],job_id,f.actor_ids[owner],operation,budget,call_mode,
             'general','generation',bytes(32),Jsonb(PRICE.as_dict())))
    return call


@pytest.mark.parametrize('actor,tenant,messages,runs',[('A-U1','A',2,1),('A-U2','A',2,1),('B-U1','B',2,1),
    ('A-ADM','A',0,0),('P-A','A',0,0),('DUAL','A',2,1),('DUAL','B',2,1)])
def test_b_owner_reads_without_tenant_where(db_fixture,b_rows,actor,tenant,messages,runs):
    async def check():
        ctx=await db_fixture.context(actor,tenant)
        async with tenant_transaction(db_fixture.pool,ctx) as conn:
            rows=await (await conn.execute('SELECT tenant_id,owner_user_id,body FROM portal.messages')).fetchall()
            assert len(rows)==messages and all(r['tenant_id']==ctx.tenant_id and r['owner_user_id']==ctx.user_id for r in rows)
            assert (await (await conn.execute('SELECT count(*) AS n FROM portal.runs')).fetchone())['n']==runs
    db_fixture.run(check())


def test_missing_context_and_raw_writes_denied(db_fixture,b_rows):
    async def check():
        async with db_fixture.pool.connection() as conn:
            for table in ['portal.messages','portal.runs']:
                assert (await (await conn.execute('SELECT count(*) AS n FROM '+table)).fetchone())['n']==0
            for query in ['SELECT config_snapshot FROM portal.runs','SELECT request_hash FROM portal.runs',
                'UPDATE portal.messages SET body=body','UPDATE portal.runs SET state=state','DELETE FROM portal.messages',
                'INSERT INTO portal.messages DEFAULT VALUES','UPDATE ops.call_attempts SET state=state',
                'DELETE FROM ops.usage_events','SELECT * FROM ops.tenant_budgets']:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):await conn.execute(query)
    db_fixture.run(check())


@pytest.mark.parametrize('mutation',['account','tenant','membership','revision','revoked','expired','idle'])
def test_b_current_revocation_same_transaction(db_fixture,b_rows,mutation):
    async def check():
        ctx=await db_fixture.context('A-U1','A')
        async with tenant_transaction(db_fixture.pool,ctx) as conn:
            assert (await (await conn.execute('SELECT count(*) AS n FROM portal.messages')).fetchone())['n']==2
            db_fixture.mutate_access(ctx,mutation)
            assert (await (await conn.execute('SELECT count(*) AS n FROM portal.messages')).fetchone())['n']==0
            assert (await (await conn.execute('SELECT count(*) AS n FROM portal.runs')).fetchone())['n']==0
    db_fixture.run(check())


def test_b_rollback_reuse_and_uncommitted_assistant_hidden(db_fixture,b_rows):
    with db_fixture.db.admin_connection() as conn:
        conn.execute("UPDATE portal.runs SET state='running',stage='generation',answer_kind=NULL,ended_at=NULL WHERE run_id=%s",(b_rows['A:A-U1'],))
    async def check():
        ctx=await db_fixture.context('A-U1','A')
        with pytest.raises(RuntimeError,match='ROLLBACK_TEST'):
            async with tenant_transaction(db_fixture.pool,ctx) as conn:
                rows=await (await conn.execute('SELECT role FROM portal.messages')).fetchall()
                assert rows==[{'role':'user'}]
                raise RuntimeError('ROLLBACK_TEST')
        async with db_fixture.pool.connection() as conn:
            assert (await (await conn.execute('SELECT count(*) AS n FROM portal.messages')).fetchone())['n']==0
        ctx=await db_fixture.context('B-U1','B')
        async with tenant_transaction(db_fixture.pool,ctx) as conn:
            assert (await (await conn.execute('SELECT count(*) AS n FROM portal.messages')).fetchone())['n']==2
    db_fixture.run(check())


@pytest.mark.parametrize('values',[{'tenant':'B'},{'owner':'A-U2'},{'session':'foreign'}, {'agent':'rules_rag'}])
def test_b_foreign_parent_owner_session_agent_rejected(db_fixture,values):
    if values.get('session')=='foreign':values={'session':db_fixture.state.session_ids['B-U1']}
    with pytest.raises((psycopg.errors.ForeignKeyViolation,psycopg.errors.CheckViolation)):
        insert_run(db_fixture,**values)


def test_messages_cannot_forge_rag_classification_or_other_run(db_fixture,b_rows):
    f=db_fixture
    for actor,run,kind in [('A-U1',b_rows['A:A-U1'],'rag_assistant'),('A-U1',b_rows['A:A-U2'],'general_assistant')]:
        with f.db.admin_connection() as conn:
            with pytest.raises((psycopg.errors.CheckViolation,psycopg.errors.ForeignKeyViolation)):
                conn.execute('INSERT INTO portal.messages(tenant_id,message_id,conversation_id,owner_user_id,agent_key,'
                    "sequence_no,role,body,run_id,payload_kind) VALUES(%s,%s,%s,%s,'general',3,'assistant','synthetic',%s,%s)",
                    (f.tenant_ids['A'],uuid4(),f.conversation_ids['A:A-U1'],f.actor_ids[actor],run,kind))
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute("UPDATE portal.messages SET payload_kind='user',role='user' WHERE run_id=%s AND role='assistant'",(b_rows['A:A-U1'],))


@pytest.mark.parametrize('values',[{'owner':'B-U1'},{'tenant':'B'},{'budget_mode':'real'}, {'job_id':'set'}, {'operation':'embed_document'}])
def test_call_binding_mode_job_rejected(db_fixture,b_rows,values):
    if values.get('job_id')=='set':values={'job_id':uuid4()}
    with pytest.raises((psycopg.errors.ForeignKeyViolation,psycopg.errors.CheckViolation)):
        insert_call(db_fixture,b_rows,**values)


def test_call_and_event_keys_snapshots_append_only(db_fixture,b_rows):
    f=db_fixture;call=insert_call(f,b_rows)
    with pytest.raises(psycopg.errors.UniqueViolation):insert_call(f,b_rows)
    with f.db.admin_connection() as conn:
        with pytest.raises(psycopg.errors.CheckViolation):conn.execute('UPDATE ops.call_attempts SET price_snapshot=%s WHERE call_id=%s',(Jsonb({}),call))
        conn.execute('INSERT INTO ops.usage_events(tenant_id,event_id,call_id,event_kind,delta_reserved_krw,'
            "delta_accounted_krw,price_snapshot) VALUES(%s,%s,%s,'reserve',3.64,0,%s)",
            (f.tenant_ids['A'],uuid4(),call,Jsonb(PRICE.as_dict())))
        for query in ['UPDATE ops.usage_events SET delta_reserved_krw=0','DELETE FROM ops.usage_events']:
            with pytest.raises(psycopg.errors.CheckViolation):conn.execute(query)
        with pytest.raises(psycopg.errors.UniqueViolation):
            conn.execute('INSERT INTO ops.usage_events(tenant_id,event_id,call_id,event_kind,delta_reserved_krw,'
                "delta_accounted_krw,price_snapshot) VALUES(%s,%s,%s,'reserve',3.64,0,%s)",
                (f.tenant_ids['A'],uuid4(),call,Jsonb(PRICE.as_dict())))


@pytest.mark.parametrize('amount',['-1','NaN'])
def test_non_finite_negative_budget_rejected(db_fixture,amount):
    f=db_fixture
    with f.db.admin_connection() as conn:
        budget=conn.execute("SELECT budget_id FROM ops.project_budget WHERE mode='mock'").fetchone()[0]
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute('INSERT INTO ops.tenant_budgets(tenant_id,budget_id,allocated_cap_krw,local_cap_krw) VALUES(%s,%s,%s,%s)',
                (f.tenant_ids['A'],budget,Decimal(amount),Decimal(amount)))


def test_meter_pool_exact_role_options_no_content_and_closed(db_fixture):
    async def check():
        async with open_meter_pool(db_fixture.db.runtime_dsn('ai_meter')) as pool:
            assert pool.timeout==2 and pool.max_size==2
            async with pool.connection() as conn:
                row=await (await conn.execute('SELECT session_user,current_user')).fetchone()
                assert row=={'session_user':'ai_meter','current_user':'ai_meter'}
                for key,expected in [('statement_timeout','5s'),('lock_timeout','2s'),('idle_in_transaction_session_timeout','5s')]:
                    assert (await (await conn.execute('SELECT current_setting(%s) AS value',(key,))).fetchone())['value']==expected
                for query in ['SELECT body FROM portal.messages','SELECT config_snapshot FROM portal.runs',
                    'UPDATE ops.call_attempts SET state=state','SELECT * FROM ops.usage_events',
                    'SELECT * FROM security.session_validate(NULL)','SET ROLE ai_web','SET ROLE ai_owner']:
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):await conn.execute(query)
        assert pool.closed
    db_fixture.run(check())
    with db_fixture.db.admin_connection() as conn:
        assert conn.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=%s AND usename='ai_meter'",(db_fixture.db.name,)).fetchone()[0]==0


def test_pool_wrong_role_and_marker_rejected(db_fixture):
    from psycopg import sql
    with pytest.raises(DatabaseBoundaryError,match='METER_CONFIGURATION_REJECTED'):make_meter_pool(db_fixture.db.runtime_dsn())
    with db_fixture.db.admin_connection() as conn:
        conn.execute(sql.SQL("COMMENT ON DATABASE {} IS 'foreign'").format(sql.Identifier(db_fixture.db.name)))
    try:
        async def check():
            with pytest.raises(DatabaseBoundaryError,match='METER_DATABASE_UNAVAILABLE'):
                async with open_meter_pool(db_fixture.db.runtime_dsn('ai_meter')):pass
        db_fixture.run(check())
        with db_fixture.db.admin_connection() as conn:
            assert conn.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=%s AND usename='ai_meter'",(db_fixture.db.name,)).fetchone()[0]==0
    finally:
        from app.db import DB_MARKER
        with db_fixture.db.admin_connection() as conn:
            conn.execute(sql.SQL('COMMENT ON DATABASE {} IS {}').format(sql.Identifier(db_fixture.db.name),sql.Literal(DB_MARKER)))


def test_web_pool_timeout_2_seconds_idle_5_seconds(db_fixture):
    async def check():
        assert db_fixture.pool.timeout==2
        async with db_fixture.pool.connection() as held:
            assert (await (await held.execute("SELECT current_setting('idle_in_transaction_session_timeout') AS n")).fetchone())['n']=='5s'
            # The second borrower really waits for the size-one pool, rather than mocked errors.
            started=asyncio.get_running_loop().time()
            with pytest.raises(PoolTimeout):
                async with db_fixture.pool.connection():pass
            elapsed=asyncio.get_running_loop().time()-started
            assert 1.8<=elapsed<3.5
    db_fixture.run(check())


def test_exact_decimal_reservations_cost_and_frozen_snapshot():
    assert reservation_krw('generate_general')==Decimal('3.64')
    assert reservation_krw('generate_rag')==Decimal('3.64')
    assert reservation_krw('embed_query')==Decimal('0.20')
    assert reservation_krw('embed_document')==Decimal('0.20')
    receipt=UsageReceipt(1000,100,1100,'gpt-4o-mini','default',None)
    assert cost_krw(receipt)==Decimal('0.51')
    with pytest.raises(FrozenInstanceError):PRICE.krw_per_usd=Decimal(1)
    with pytest.raises(ValueError):cost_krw(UsageReceipt(True,0,1,'gpt-4o-mini','default',None))
    with pytest.raises(ValueError):cost_krw(UsageReceipt(1,1,99,'gpt-4o-mini','default',None))
    with pytest.raises(ValueError):cost_krw(UsageReceipt(1,0,1,'other-model','default',None))
    with pytest.raises(ValueError):cost_krw(UsageReceipt(1,0,1,'gpt-4o-mini','priority',None))
    outcome=ProviderOutcome('synthetic-private-marker',receipt,'observed',None)
    claim=DispatchClaim(uuid4(),1,'synthetic-claim-marker')
    assert 'synthetic-private-marker' not in repr(outcome) and 'synthetic-claim-marker' not in repr(claim)


@pytest.mark.parametrize('setting',['app.user_id','app.tenant_id','app.session_id'])
@pytest.mark.parametrize('value',['','malformed'])
def test_b_malformed_context_denies(db_fixture,b_rows,setting,value):
    async def check():
        ctx=await db_fixture.context('A-U1','A')
        async with tenant_transaction(db_fixture.pool,ctx) as conn:
            await conn.execute('SELECT set_config(%s,%s,true)',(setting,value))
            for table in ['portal.messages','portal.runs']:
                assert (await (await conn.execute('SELECT count(*) AS n FROM '+table)).fetchone())['n']==0
    db_fixture.run(check())


def test_exhausted_live_http_pool_returns_safe_503(client,login):
    from contextlib import AsyncExitStack
    import threading
    login(client,'A-U1')
    ready=threading.Event();release=asyncio.Event()
    async def hold_all():
        async with AsyncExitStack() as stack:
            for _ in range(4):await stack.enter_async_context(client.app.state.pool.connection())
            ready.set();await release.wait()
    future=client.portal.start_task_soon(hold_all)
    assert ready.wait(5)
    try:
        import time
        start=time.monotonic();reply=client.get('/api/v1/auth/me')
        assert reply.status_code==503 and 1.8<=time.monotonic()-start<3.5
        assert reply.headers['cache-control']=='no-store'
        assert 'password' not in reply.text.lower() and 'dsn' not in reply.text.lower()
    finally:
        async def unblock():release.set()
        client.portal.call(unblock);future.result(timeout=5)


@pytest.mark.parametrize('counts',[
    {'input_tokens':'private-data','output_tokens':0,'total_tokens':0},
    {'input_tokens':True,'output_tokens':0,'total_tokens':1},
    {'input_tokens':1,'output_tokens':1,'total_tokens':99},
    {'input_tokens':1,'output_tokens':0,'total_tokens':1,'prompt':'private-data'},
    {'input_tokens':1.5,'output_tokens':0,'total_tokens':1.5}])
def test_usage_event_rejects_untyped_or_extra_payload(db_fixture,b_rows,counts):
    f=db_fixture;call=insert_call(f,b_rows)
    with f.db.admin_connection() as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute('INSERT INTO ops.usage_events(tenant_id,event_id,call_id,event_kind,delta_reserved_krw,'
                "delta_accounted_krw,token_counts,price_snapshot) VALUES(%s,%s,%s,'settle',-3.64,0.51,%s,%s)",
                (f.tenant_ids['A'],uuid4(),call,Jsonb(counts),Jsonb(PRICE.as_dict())))


def test_settle_release_mutually_exclusive_storage_key(db_fixture,b_rows):
    f=db_fixture;call=insert_call(f,b_rows)
    with f.db.admin_connection() as conn:
        query='INSERT INTO ops.usage_events(tenant_id,event_id,call_id,event_kind,delta_reserved_krw,delta_accounted_krw,price_snapshot) VALUES(%s,%s,%s,%s,-3.64,%s,%s)'
        conn.execute(query,(f.tenant_ids['A'],uuid4(),call,'settle',Decimal('0.51'),Jsonb(PRICE.as_dict())))
        with pytest.raises(psycopg.errors.UniqueViolation):
            conn.execute(query,(f.tenant_ids['A'],uuid4(),call,'release',0,Jsonb(PRICE.as_dict())))
