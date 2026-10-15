import asyncio
import hashlib
import shutil
from datetime import date
from uuid import UUID,uuid4
from psycopg import sql
from scripts.migrate import MIGRATIONS,create_fixture_database,apply_migrations
from scripts.seed import seed_fixture
from app.db import make_web_pool,tenant_transaction
from support import FixtureState


def fingerprint(conn):
    tables=conn.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname IN ('security','portal','rag','ops') ORDER BY 1,2").fetchall()
    result={}
    for schema,table in tables:
        expr="to_jsonb(t)-ARRAY['asset_id','asset_revision','asset_version_id','asset_config_hash']" if (schema,table)==('portal','runs') else 'to_jsonb(t)'
        result[(schema,table)]=conn.execute(sql.SQL("SELECT count(*),md5(COALESCE(string_agg(("+expr+")::text,'' ORDER BY ("+expr+")::text),'')) FROM {}.{} t").format(sql.Identifier(schema),sql.Identifier(table))).fetchone()
    return result


def test_028_preserves_historical_run_all_rows_checksums_and_rerun(owned_cluster,tmp_path):
    old=tmp_path/'old';old.mkdir()
    for path in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
        if path.name<'028_':shutil.copy2(path,old/path.name)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in old.iterdir()}
    db=create_fixture_database();state=None;pool=None;loop=asyncio.new_event_loop()
    try:
        apply_migrations(db,old);state=seed_fixture(db);pool=make_web_pool(db.runtime_dsn(),size=1)
        loop.run_until_complete(pool.open());loop.run_until_complete(pool.wait(timeout=5))
        f=FixtureState(db,state,loop,pool,'',state.passwords)
        with db.admin_connection() as conn:
            conn.execute("UPDATE portal.agent_configs SET enabled=true WHERE agent_key='general'")
            for tenant in state.tenant_ids.values():
                for bid, in conn.execute('SELECT budget_id FROM ops.project_budget').fetchall():conn.execute('INSERT INTO ops.tenant_budgets(tenant_id,budget_id,allocated_cap_krw,local_cap_krw) VALUES(%s,%s,12500,12500)',(tenant,bid))
        async def old_admit():
            ctx=await f.context('A-U1','A');send=uuid4();request_hash=hashlib.sha256(b'old-private-question').digest()
            async with tenant_transaction(pool,ctx) as conn:
                ready=(await (await conn.execute('SELECT security.run_prepare(%s,%s,%s,%s,%s,%s,%s,%s) AS data',(ctx.session_id,ctx.tenant_id,'general',None,send,request_hash,date(2026,10,1),'mock'))).fetchone())['data']
                data=(await (await conn.execute('SELECT security.run_admit(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) AS data',(ctx.session_id,ctx.tenant_id,'general',None,send,request_hash,'합성 과거 질문',date(2026,10,1),'mock',ready['config_version'],[],30,b'x'*32,uuid4()))).fetchone())['data']
                return ctx,UUID(data['run_id'])
        ctx,rid=loop.run_until_complete(old_admit())
        with db.admin_connection() as conn:before=fingerprint(conn)
        through=tmp_path/'through-028';through.mkdir()
        for path in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
            if path.name<'029_':shutil.copy2(path,through/path.name)
        assert apply_migrations(db,through)==['028_run_asset_binding.sql']
        with db.admin_connection() as conn:
            assert fingerprint(conn)==before
            assert dict(conn.execute("SELECT version,sha256 FROM infra.schema_migrations WHERE version<'028_' ").fetchall())==hashes
            assert conn.execute('SELECT asset_id,asset_revision,asset_version_id,asset_config_hash FROM portal.runs WHERE run_id=%s',(rid,)).fetchone()==(None,None,None,None)
            assert not conn.execute("SELECT has_column_privilege('ai_web','portal.runs','asset_revision','UPDATE')").fetchone()[0]
            assert conn.execute("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='portal.runs'::regclass").fetchone()[0]
            for role in ['ai_index','ai_meter']:
                assert not conn.execute("SELECT has_function_privilege(%s,'security.run_asset_resolve(uuid,uuid,text,uuid)','EXECUTE')",(role,)).fetchone()[0]
        async def old_read_claim():
            from app.ai.repository import CallRepository
            async with tenant_transaction(pool,ctx) as conn:
                view=(await (await conn.execute("SELECT security.run_read(%s,%s,'run',%s,NULL,20) AS data",(ctx.session_id,ctx.tenant_id,rid))).fetchone())['data']
                assert view['asset_binding'] is None
            repo=CallRepository(pool,None,date(2026,10,1));ticket=await repo.claim(ctx,rid,'mock')
            assert ticket.asset_binding is None
            await repo.fail(ticket,'EXECUTION_INTERRUPTED')
        loop.run_until_complete(old_read_claim())
        assert apply_migrations(db,through)==[]
    finally:
        if pool:loop.run_until_complete(pool.close())
        loop.close();db.drop()
        if state:state.secret_path.unlink(missing_ok=True)
