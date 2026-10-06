from datetime import date
from uuid import UUID
import pytest
from app.types import AuthContext
from app.db import open_index_pool,open_meter_pool
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage
from app.documents.worker import DocumentWorker
from app.documents.embedding import EmbeddingGateway,MockEmbeddingProvider
from test_operations import ops_rows,headers
from test_document_ingest import metadata,RAW

@pytest.mark.parametrize('boundary',['before_claim','after_dispatch','after_checkpoint'])
@pytest.mark.parametrize('session_change',['logout','expired','idle'])
def test_index_job_uses_saved_principal_not_http_session(client,login,ops_rows,tmp_path,boundary,session_change):
    f=ops_rows;csrf=login(client,'A-ADM')['csrf_token']
    with f.db.admin_connection() as c:sid=c.execute('SELECT session_id FROM security.sessions WHERE user_id=%s AND revoked_at IS NULL ORDER BY issued_at DESC LIMIT 1',(f.actor_ids['A-ADM'],)).fetchone()[0]
    ctx=AuthContext(sid,f.actor_ids['A-ADM'],f.tenant_ids['A'],'TADMIN','')
    def invalidate():
        if session_change=='logout':assert client.post('/api/v1/auth/logout',headers=headers(f,csrf=csrf)).status_code==200
        else:f.mutate_access(ctx,session_change)
        assert client.get('/api/v1/admin/jobs',headers=headers(f)).status_code==401
    async def check():
        documents=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40);ids=await documents.register(ctx,metadata(),RAW);job=UUID(ids['job_id']);calls=[]
        class Provider(MockEmbeddingProvider):
            async def embed(self,*args):
                calls.append(args[0]);result=await super().embed(*args)
                if boundary=='after_dispatch':invalidate()
                return result
        if boundary=='before_claim':invalidate()
        async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            worker=DocumentWorker(documents,EmbeddingGateway(index,meter,Provider(),date(2026,10,1)));save=worker._save_batch
            async def checkpoint(*args):
                await save(*args)
                if boundary=='after_checkpoint':invalidate()
            worker._save_batch=checkpoint
            if boundary=='before_claim':
                async with f.pool.connection() as c:
                    pending=(await (await c.execute("SELECT security.document_pending('mock') AS data")).fetchone())['data'];assert str(job) in {x['job_id'] for x in pending}
            await worker.run(ctx,job)
            assert len(calls)==1
        with f.db.admin_connection() as c:
            assert c.execute('SELECT state,origin_session_id FROM rag.jobs WHERE job_id=%s',(job,)).fetchone()==('completed',sid)
            assert c.execute('SELECT count(*) FROM security.document_publications WHERE document_id=%s AND active',(ids['document_id'],)).fetchone()[0]==1
            assert c.execute('SELECT state,slot_held FROM ops.call_attempts WHERE job_id=%s',(job,)).fetchone()==('settled',False)
            assert c.execute("SELECT count(*) FROM ops.usage_events WHERE event_kind='settle'").fetchone()[0]==1
    f.run(check())


@pytest.mark.parametrize('boundary',['before_claim','after_dispatch'])
@pytest.mark.parametrize('revocation',['account','tenant','membership','role','managed','deleted','agent'])
def test_session_independence_keeps_current_principal_and_document_gate(ops_rows,tmp_path,boundary,revocation):
    f=ops_rows
    async def check():
        actor='P-A' if revocation=='managed' else 'A-ADM';ctx=await f.context(actor,'A');documents=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
        ids=await documents.register(ctx,metadata(),RAW);job=UUID(ids['job_id']);calls=[]
        def revoke():
            if revocation in ('account','tenant','membership'):f.mutate_access(ctx,revocation)
            else:
                with f.db.admin_connection() as c:
                    if revocation=='role':c.execute("UPDATE security.memberships SET role='USER' WHERE user_id=%s AND tenant_id=%s",(ctx.user_id,ctx.tenant_id))
                    elif revocation=='managed':c.execute('UPDATE security.managed_tenants SET active=false WHERE user_id=%s',(ctx.user_id,))
                    elif revocation=='deleted':c.execute('UPDATE security.document_access SET deleted_at=clock_timestamp() WHERE document_id=%s',(ids['document_id'],))
                    else:c.execute("UPDATE portal.agent_configs SET enabled=false WHERE tenant_id=%s AND agent_key='rules_rag'",(ctx.tenant_id,))
        class Provider(MockEmbeddingProvider):
            async def embed(self,*args):
                calls.append(args[0]);result=await super().embed(*args)
                if boundary=='after_dispatch':revoke()
                return result
        if boundary=='before_claim':revoke()
        async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            with pytest.raises(Exception):await DocumentWorker(documents,EmbeddingGateway(index,meter,Provider(),date(2026,10,1))).run(ctx,job)
        assert len(calls)==int(boundary=='after_dispatch')
        with f.db.admin_connection() as c:
            assert c.execute('SELECT count(*) FROM security.document_publications WHERE document_id=%s AND active',(ids['document_id'],)).fetchone()[0]==0
            assert c.execute("SELECT reserved_krw,active_slot FROM ops.project_budget WHERE mode='mock'").fetchone()==(0,0)
            assert c.execute("SELECT count(*) FROM ops.call_attempts WHERE job_id=%s AND state='settled'",(job,)).fetchone()[0]==int(boundary=='after_dispatch')
    f.run(check())

@pytest.mark.parametrize('role',['ai_web','ai_meter'])
def test_http_and_meter_roles_cannot_use_background_claim(ops_rows,tmp_path,role):
    import psycopg
    from uuid import uuid4
    f=ops_rows
    with f.role_connection(role) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute("SELECT security.document_background_control(%s,%s,%s,'claim',NULL,%s,'{}'::jsonb)",(f.actor_ids['A-ADM'],f.tenant_ids['A'],uuid4(),b'x'*32))

@pytest.mark.parametrize('proof',['foreign_actor','foreign_tenant','wrong_epoch','wrong_claim'])
def test_background_control_saved_binding_and_epoch_are_not_forgeable(ops_rows,tmp_path,proof):
    f=ops_rows
    async def check():
        ctx=await f.context('A-ADM','A');documents=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40);ids=await documents.register(ctx,metadata(),RAW);job=UUID(ids['job_id']);claim=b'k'*32
        async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            gateway=EmbeddingGateway(index,meter,MockEmbeddingProvider(),date(2026,10,1));args=(ctx.user_id,ctx.tenant_id,job)
            if proof.startswith('foreign'):
                args=(f.actor_ids['B-ADM'],ctx.tenant_id,job) if proof=='foreign_actor' else (ctx.user_id,f.tenant_ids['B'],job)
                with pytest.raises(Exception):await gateway.rpc('document_background_control',(*args,'claim',None,claim,__import__('psycopg').types.json.Jsonb({'mode':'mock'})))
            else:
                from psycopg.types.json import Jsonb
                owned=await gateway.rpc('document_background_control',(*args,'claim',None,claim,Jsonb({'mode':'mock'})))
                with pytest.raises(Exception):await gateway.rpc('document_background_control',(*args,'heartbeat',owned['epoch']+1 if proof=='wrong_epoch' else owned['epoch'],b'z'*32 if proof=='wrong_claim' else claim,Jsonb({})))
            with f.db.admin_connection() as c:assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==0
    f.run(check())


@pytest.mark.parametrize('state',['queued','unknown','membership_revoked'])
def test_native_restart_after_logout_preserves_job_and_call_ledger(ops_rows,auth_settings,tmp_path,state):
    import time,httpx
    from uuid import uuid4
    from test_auth_restart import LiveServer,BASE_URL,WRITE
    from test_document_api import multipart
    f=ops_rows;server=LiveServer(f,auth_settings);root=tmp_path/'native-sources'
    server.env.update(AI_SOURCE_ROOT=str(root),AI_INDEX_ENABLED='false',AI_INDEX_DSN=f.db.runtime_dsn('ai_index'),AI_METER_DSN=f.db.runtime_dsn('ai_meter'))
    server.secrets += [server.env['AI_INDEX_DSN'],server.env['AI_METER_DSN']]
    try:
        server.start()
        with httpx.Client(base_url=BASE_URL,timeout=5,trust_env=False) as client:
            csrf=server.login(client,'A-ADM');h={**WRITE,'X-CSRF-Token':csrf,'X-Tenant-ID':str(f.tenant_ids['A'])};read={'X-Tenant-ID':str(f.tenant_ids['A'])}
            reply=client.post('/api/v1/admin/documents',headers=h,files=multipart({'client_upload_id':str(uuid4()),'title':'합성 재시작 자료','media_type':'text/plain'},RAW));assert reply.status_code==202;ids=reply.json()['data'];job=UUID(ids['job_id'])
            with f.db.admin_connection() as c:sid=c.execute('SELECT origin_session_id FROM rag.jobs WHERE job_id=%s',(job,)).fetchone()[0]
            ctx=AuthContext(sid,f.actor_ids['A-ADM'],f.tenant_ids['A'],'TADMIN','')
            if state=='unknown':
                class Unknown(MockEmbeddingProvider):
                    async def embed(self,*args):raise TimeoutError('synthetic remote unknown')
                async def run():
                    documents=DocumentRepository(f.pool,SourceStorage(root),auth_settings.login_hmac_secret.get_secret_value())
                    async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
                        with pytest.raises(TimeoutError):await DocumentWorker(documents,EmbeddingGateway(index,meter,Unknown(),date(2026,10,1))).run(ctx,job)
                f.run(run())
            assert client.post('/api/v1/auth/logout',headers=h).status_code==200
            if state=='membership_revoked':f.mutate_access(ctx,'membership')
            with f.db.admin_connection() as c:
                before=c.execute("SELECT accounted_krw,reserved_krw,active_slot FROM ops.project_budget WHERE mode='mock'").fetchone()
                before_calls=c.execute('SELECT call_id,state,slot_held FROM ops.call_attempts ORDER BY call_id').fetchall()
            server.env['AI_INDEX_ENABLED']='true';server.restart()
            deadline=time.monotonic()+8
            expected='completed' if state=='queued' else 'needs_review' if state=='unknown' else 'blocked'
            while time.monotonic()<deadline:
                with f.db.admin_connection() as c:actual=c.execute('SELECT state FROM rag.jobs WHERE job_id=%s',(job,)).fetchone()[0]
                if actual==expected:break
                time.sleep(.05)
            assert actual==expected
            assert client.get('/api/v1/admin/jobs/'+str(job),headers=read).status_code==401
            with f.db.admin_connection() as c:
                assert c.execute('SELECT origin_session_id FROM rag.jobs WHERE job_id=%s',(job,)).fetchone()[0]==sid
                assert c.execute('SELECT count(*) FROM rag.jobs').fetchone()[0]==1
                after=c.execute("SELECT accounted_krw,reserved_krw,active_slot FROM ops.project_budget WHERE mode='mock'").fetchone()
                calls=c.execute('SELECT call_id,state,slot_held FROM ops.call_attempts ORDER BY call_id').fetchall()
                if state=='queued':assert len(calls)==1 and calls[0][1:]==('settled',False) and after[0]>before[0] and after[1:]==(0,0)
                else:assert after==before and calls==before_calls
            server.restart()
            with f.db.admin_connection() as c:
                assert c.execute('SELECT call_id,state,slot_held FROM ops.call_attempts ORDER BY call_id').fetchall()==calls
                assert c.execute("SELECT accounted_krw,reserved_krw,active_slot FROM ops.project_budget WHERE mode='mock'").fetchone()==after
            if state!='membership_revoked':
                server.login(client,'A-ADM');view=client.get('/api/v1/admin/jobs/'+str(job),headers=read);assert view.status_code==200 and view.json()['data']['state']==expected
    finally:server.stop();server.log.close()
