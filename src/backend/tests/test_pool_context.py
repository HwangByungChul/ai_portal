import asyncio
from dataclasses import replace
from uuid import uuid4
import pytest
from pydantic import SecretStr
from fastapi.testclient import TestClient
from app.config import Settings
from app.db import DatabaseBoundaryError,make_web_pool,open_web_pool,tenant_transaction
from app.main import create_app

async def safe_returned_connection(fixture,pid):
    async with fixture.pool.connection() as conn:
        row=await (await conn.execute("SELECT pg_backend_pid() AS pid,"
            "NULLIF(current_setting('app.user_id',true),'') AS user_id,"
            "NULLIF(current_setting('app.tenant_id',true),'') AS tenant_id,"
            "NULLIF(current_setting('app.session_id',true),'') AS session_id")).fetchone()
        assert row == {'pid':pid,'user_id':None,'tenant_id':None,'session_id':None}
        assert await (await conn.execute('SELECT * FROM portal.conversations')).fetchall()==[]
    ctx=await fixture.context('B-U1','B')
    async with tenant_transaction(fixture.pool,ctx) as conn:
        rows=await (await conn.execute('SELECT * FROM portal.conversations')).fetchall()
        assert len(rows)==1 and rows[0]['tenant_id']==ctx.tenant_id

@pytest.mark.parametrize('exit_kind',['normal','rollback','cancel'])
def test_same_connection_cleanup(db_fixture,exit_kind):
    async def check():
        ctx=await db_fixture.context('A-U1','A')
        pid=None; entered=asyncio.Event()
        async def work():
            nonlocal pid
            async with tenant_transaction(db_fixture.pool,ctx) as conn:
                pid=(await (await conn.execute('SELECT pg_backend_pid() AS pid')).fetchone())['pid']
                assert len(await (await conn.execute('SELECT * FROM portal.conversations')).fetchall())==1
                if exit_kind=='rollback': raise RuntimeError('EXPECTED_ROLLBACK')
                if exit_kind=='cancel':
                    entered.set(); await asyncio.Event().wait()
        if exit_kind=='rollback':
            with pytest.raises(RuntimeError,match='EXPECTED_ROLLBACK'): await work()
        elif exit_kind=='cancel':
            task=asyncio.create_task(work());await entered.wait();task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
        else: await work()
        await safe_returned_connection(db_fixture,pid)
    db_fixture.run(check())


def test_concurrent_tenants_do_not_mix(db_fixture):
    async def check():
        async with open_web_pool(db_fixture.db.runtime_dsn(),size=2) as pool:
            barrier=asyncio.Barrier(2)
            async def worker(actor,tenant):
                ctx=await db_fixture.context(actor,tenant)
                async with tenant_transaction(pool,ctx) as conn:
                    await barrier.wait()
                    for _ in range(3):
                        rows=await (await conn.execute('SELECT * FROM portal.conversations')).fetchall()
                        assert len(rows)==1 and rows[0]['tenant_id']==ctx.tenant_id and rows[0]['owner_user_id']==ctx.user_id
                        await asyncio.sleep(0)
            await asyncio.gather(worker('A-U1','A'),worker('B-U1','B'))
    db_fixture.run(check())


def test_internal_context_mismatch_and_missing_tenant_fail(db_fixture):
    async def check():
        ctx=await db_fixture.context('A-U1','A')
        for invalid in (replace(ctx,tenant_id=None),replace(ctx,user_id=uuid4())):
            with pytest.raises(ValueError):
                async with tenant_transaction(db_fixture.pool,invalid): pass
    db_fixture.run(check())


def test_app_lifespan_uses_web_pool_and_closes(db_fixture):
    settings=Settings(web_dsn=SecretStr(db_fixture.db.runtime_dsn()))
    app=create_app(settings,health_only=True)
    with TestClient(app) as client:
        assert client.get('/api/v1/health').status_code==200
        pool=app.state.pool
        assert not pool.closed
    assert pool.closed


def test_startup_rejects_admin_dsn(db_fixture):
    with pytest.raises(DatabaseBoundaryError,match='WEB_CONFIGURATION_REJECTED'):
        make_web_pool('host=127.0.0.1 port=55432 dbname='+db_fixture.db.name+' user=mvp_bootstrap')


def test_startup_rejects_foreign_marker(db_fixture):
    from psycopg import sql
    with db_fixture.db.admin_connection() as conn:
        conn.execute(sql.SQL("COMMENT ON DATABASE {} IS 'other-project'").format(sql.Identifier(db_fixture.db.name)))
    try:
        async def check():
            with pytest.raises(DatabaseBoundaryError,match='WEB_DATABASE_UNAVAILABLE'):
                async with open_web_pool(db_fixture.db.runtime_dsn()): pass
        db_fixture.run(check())
        with db_fixture.db.admin_connection() as conn:
            # Only the fixture's original pool connection remains; rejected startups leaked none.
            assert conn.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=%s AND usename='ai_web'",
                (db_fixture.db.name,)).fetchone()[0]==1
    finally:
        from app.db import DB_MARKER
        with db_fixture.db.admin_connection() as conn:
            conn.execute(sql.SQL('COMMENT ON DATABASE {} IS {}').format(sql.Identifier(db_fixture.db.name),sql.Literal(DB_MARKER)))
