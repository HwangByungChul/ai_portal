from datetime import date
from uuid import UUID
import pytest
from app.types import AuthContext
from app.db import open_index_pool,open_meter_pool
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage
from app.documents.worker import DocumentWorker
from app.documents.manager import DocumentManager
from app.documents.embedding import EmbeddingGateway,MockEmbeddingProvider
from test_operations import ops_rows,headers
from test_document_ingest import metadata,RAW

@pytest.mark.parametrize('session_change',['logout','expired','idle'])
@pytest.mark.parametrize('boundary',['before_claim','after_purge','before_finish'])
def test_cleanup_survives_http_session_end(client,login,ops_rows,tmp_path,session_change,boundary):
    f=ops_rows;csrf=login(client,'A-ADM')['csrf_token']
    with f.db.admin_connection() as c:sid=c.execute('SELECT session_id FROM security.sessions WHERE user_id=%s AND revoked_at IS NULL ORDER BY issued_at DESC LIMIT 1',(f.actor_ids['A-ADM'],)).fetchone()[0]
    ctx=AuthContext(sid,f.actor_ids['A-ADM'],f.tenant_ids['A'],'TADMIN','')
    def invalidate():
        if session_change=='logout':assert client.post('/api/v1/auth/logout',headers=headers(f,csrf=csrf)).status_code==200
        else:f.mutate_access(ctx,session_change)
        assert client.get('/api/v1/admin/jobs',headers=headers(f)).status_code==401
    async def check():
        documents=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40);ids=await documents.register(ctx,metadata(),RAW);doc=UUID(ids['document_id'])
        reply=client.request('DELETE','/api/v1/admin/documents/'+str(doc),headers=headers(f,csrf=csrf),json={'expected_revision':1});assert reply.status_code==200
        if boundary=='before_claim':invalidate()
        async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            gateway=EmbeddingGateway(index,meter,MockEmbeddingProvider(),date(2026,10,1));original=gateway.rpc
            async def rpc(name,args):
                if name=='document_cleanup_background' and args[4]=='finish' and boundary=='before_finish':invalidate()
                result=await original(name,args)
                if name=='document_cleanup_background' and args[4]=='purge' and boundary=='after_purge':invalidate()
                return result
            gateway.rpc=rpc
            await DocumentManager(DocumentWorker(documents,gateway),'mock').cleanup(ctx,doc)
        with f.db.admin_connection() as c:
            assert c.execute("SELECT count(*) FROM rag.jobs WHERE job_kind='internal_cleanup' AND state='completed'").fetchone()[0]==1
            assert c.execute('SELECT count(*) FROM rag.document_versions WHERE payload_purged AND title IS NULL AND source_object_key IS NULL').fetchone()[0]==1
            assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==0
        assert not list((tmp_path/'sources').rglob('source'))
    f.run(check())

@pytest.mark.parametrize('boundary',['before_claim','after_purge'])
@pytest.mark.parametrize('revocation',['account','tenant','membership','role','managed'])
def test_cleanup_rechecks_current_principal(ops_rows,tmp_path,boundary,revocation):
    f=ops_rows
    async def check():
        actor='P-A' if revocation=='managed' else 'A-ADM';ctx=await f.context(actor,'A');repo=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40);ids=await repo.register(ctx,metadata(),RAW);doc=UUID(ids['document_id']);await repo.delete(ctx,doc,1)
        def revoke():
            with f.db.admin_connection() as c:
                if revocation=='account':c.execute('UPDATE security.accounts SET active=false WHERE user_id=%s',(ctx.user_id,))
                elif revocation=='tenant':c.execute('UPDATE security.tenants SET active=false WHERE tenant_id=%s',(ctx.tenant_id,))
                elif revocation=='membership':c.execute('UPDATE security.memberships SET active=false WHERE tenant_id=%s AND user_id=%s',(ctx.tenant_id,ctx.user_id))
                elif revocation=='role':c.execute("UPDATE security.memberships SET role='USER' WHERE tenant_id=%s AND user_id=%s",(ctx.tenant_id,ctx.user_id))
                else:c.execute('UPDATE security.managed_tenants SET active=false WHERE tenant_id=%s AND user_id=%s',(ctx.tenant_id,ctx.user_id))
        async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            gateway=EmbeddingGateway(index,meter,MockEmbeddingProvider(),date(2026,10,1));original=gateway.rpc
            async def rpc(name,args):
                result=await original(name,args)
                if args[4]=='purge' and boundary=='after_purge':revoke()
                return result
            gateway.rpc=rpc
            if boundary=='before_claim':revoke()
            with pytest.raises(Exception):await DocumentManager(DocumentWorker(repo,gateway),'mock').cleanup(ctx,doc)
        assert len(list((tmp_path/'sources').rglob('source')))==1
        with f.db.admin_connection() as c:
            assert c.execute("SELECT count(*) FROM rag.jobs WHERE job_kind='internal_cleanup' AND state='completed'").fetchone()[0]==0
            assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==0
    f.run(check())

@pytest.mark.parametrize('role',['ai_web','ai_meter'])
def test_cleanup_service_capability_is_index_only(ops_rows,role):
    import psycopg
    from uuid import uuid4
    f=ops_rows
    with f.role_connection(role) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute("SELECT security.document_cleanup_background(%s,%s,%s,%s,'claim','mock',NULL,%s)",(f.actor_ids['A-ADM'],f.tenant_ids['A'],uuid4(),uuid4(),b'x'*32))

@pytest.mark.parametrize('proof',['actor','tenant','document','mode','index_job','live_document','claim','epoch','lease','deletion_revision','finish_before_purge'])
def test_cleanup_saved_binding_cannot_be_forged(ops_rows,tmp_path,proof):
    from uuid import uuid4
    f=ops_rows
    async def check():
        ctx=await f.context('A-ADM','A');repo=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40);ids=await repo.register(ctx,metadata(),RAW);doc=UUID(ids['document_id'])
        if proof!='live_document':await repo.delete(ctx,doc,1)
        with f.db.admin_connection() as c:
            row=c.execute("SELECT job_id FROM rag.jobs WHERE document_id=%s AND job_kind='internal_cleanup'",(doc,)).fetchone();job=row[0] if row else UUID(ids['job_id'])
        async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            g=EmbeddingGateway(index,meter,MockEmbeddingProvider(),date(2026,10,1));claim=b'k'*32
            base=[ctx.user_id,ctx.tenant_id,doc,job,'claim','mock',None,claim]
            if proof in ('actor','tenant','document','mode','index_job','live_document'):
                if proof=='actor':base[0]=f.actor_ids['B-ADM']
                if proof=='tenant':base[1]=f.tenant_ids['B']
                if proof=='document':base[2]=uuid4()
                if proof=='mode':base[5]='real'
                if proof=='index_job':base[3]=UUID(ids['job_id'])
                with pytest.raises(Exception):await g.rpc('document_cleanup_background',tuple(base))
            else:
                owned=await g.rpc('document_cleanup_background',tuple(base));base[4]='purge';base[6]=owned['epoch']
                if proof=='claim':base[7]=b'z'*32
                if proof=='epoch':base[6]+=1
                if proof=='finish_before_purge':base[4]='finish'
                with f.db.admin_connection() as c:
                    if proof=='lease':c.execute("UPDATE security.job_authorizations SET expires_at=clock_timestamp()-interval '1 second' WHERE job_id=%s",(job,))
                    if proof=='deletion_revision':c.execute('UPDATE security.document_access SET acl_revision=acl_revision+1 WHERE document_id=%s',(doc,))
                with pytest.raises(Exception):await g.rpc('document_cleanup_background',tuple(base))
            with f.db.admin_connection() as c:
                assert c.execute('SELECT count(*) FROM rag.document_versions WHERE payload_purged').fetchone()[0]==0
                assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==0
        assert len(list((tmp_path/'sources').rglob('source')))==1
    f.run(check())

@pytest.mark.parametrize('fault',[False,True])
@pytest.mark.parametrize('session_change',['logout','expired','idle'])
def test_native_cleanup_recovers_same_database_after_session_end(ops_rows,auth_settings,tmp_path,session_change,fault):
    import httpx,time
    from uuid import uuid4
    from test_auth_restart import LiveServer,BASE_URL,WRITE
    from test_document_api import multipart
    f=ops_rows;server=LiveServer(f,auth_settings);root=tmp_path/'native-sources'
    server.env.update(AI_SOURCE_ROOT=str(root),AI_INDEX_ENABLED='false',AI_INDEX_DSN=f.db.runtime_dsn('ai_index'),AI_METER_DSN=f.db.runtime_dsn('ai_meter'));server.secrets += [server.env['AI_INDEX_DSN'],server.env['AI_METER_DSN']]
    try:
        server.start()
        with httpx.Client(base_url=BASE_URL,timeout=5,trust_env=False) as client:
            csrf=server.login(client,'A-ADM');h={**WRITE,'X-CSRF-Token':csrf,'X-Tenant-ID':str(f.tenant_ids['A'])};read={'X-Tenant-ID':str(f.tenant_ids['A'])}
            reply=client.post('/api/v1/admin/documents',headers=h,files=multipart({'client_upload_id':str(uuid4()),'title':'정리 합성 자료','media_type':'text/plain'},RAW));assert reply.status_code==202;doc=reply.json()['data']['document_id']
            assert client.request('DELETE','/api/v1/admin/documents/'+doc,headers=h,json={'expected_revision':1}).status_code==200
            with f.db.admin_connection() as c:
                job,origin=c.execute("SELECT job_id,origin_session_id FROM rag.jobs WHERE document_id=%s AND job_kind='internal_cleanup'",(doc,)).fetchone();before=c.execute("SELECT * FROM ops.project_budget ORDER BY mode").fetchall()
            if fault:
                class BrokenStorage(SourceStorage):
                    def remove(self,*args,**kwargs):raise OSError('synthetic cleanup source failure')
                async def partial():
                    repo=DocumentRepository(f.pool,BrokenStorage(root),'x'*40)
                    async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
                        manager=DocumentManager(DocumentWorker(repo,EmbeddingGateway(index,meter,MockEmbeddingProvider(),date(2026,10,1))),'mock')
                        with pytest.raises(OSError):await manager.cleanup(AuthContext(origin,f.actor_ids['A-ADM'],f.tenant_ids['A'],'TADMIN',''),UUID(doc))
                f.run(partial())
                with f.db.admin_connection() as c:
                    assert c.execute('SELECT state FROM rag.jobs WHERE job_id=%s',(job,)).fetchone()[0]=='queued'
                    assert c.execute('SELECT count(*) FROM rag.document_versions WHERE payload_purged').fetchone()[0]==1
                assert len(list(root.rglob('source')))==1
            if session_change=='logout':assert client.post('/api/v1/auth/logout',headers=h).status_code==200
            else:f.mutate_access(AuthContext(origin,f.actor_ids['A-ADM'],f.tenant_ids['A'],'TADMIN',''),session_change)
            server.env['AI_INDEX_ENABLED']='true';server.restart();deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                with f.db.admin_connection() as c:state=c.execute('SELECT state FROM rag.jobs WHERE job_id=%s',(job,)).fetchone()[0]
                if state=='completed':break
                time.sleep(.05)
            assert state=='completed';assert client.get('/api/v1/admin/jobs/'+str(job),headers=read).status_code==401
            server.restart()
            with f.db.admin_connection() as c:
                assert c.execute('SELECT state,origin_session_id FROM rag.jobs WHERE job_id=%s',(job,)).fetchone()==('completed',origin)
                assert c.execute('SELECT count(*) FROM rag.jobs').fetchone()[0]==2
                assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==0
                assert c.execute("SELECT * FROM ops.project_budget ORDER BY mode").fetchall()==before
                assert c.execute('SELECT count(*) FROM rag.document_versions WHERE payload_purged AND title IS NULL AND source_object_key IS NULL').fetchone()[0]==1
            assert not list(root.rglob('source'))
            server.login(client,'A-ADM');assert client.get('/api/v1/admin/jobs/'+str(job),headers=read).json()['data']['state']=='completed'
            server.log.flush();raw=server.log_path.read_text();assert all(not secret or secret not in raw for secret in server.secrets)
    finally:server.stop();server.log.close()


def test_two_connections_claim_one_cleanup_lease(ops_rows,tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    f=ops_rows
    async def admit():
        ctx=await f.context('A-ADM','A');repo=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40);ids=await repo.register(ctx,metadata(),RAW);doc=UUID(ids['document_id']);await repo.delete(ctx,doc,1);return ctx,doc
    ctx,doc=f.run(admit())
    with f.db.admin_connection() as c:job,initial_epoch=c.execute("SELECT job_id,lease_epoch FROM rag.jobs WHERE document_id=%s AND job_kind='internal_cleanup'",(doc,)).fetchone()
    barrier=Barrier(2)
    def claim(value):
        with f.role_connection('ai_index') as c:
            barrier.wait(timeout=5)
            return c.execute("SELECT security.document_cleanup_background(%s,%s,%s,%s,'claim','mock',NULL,%s)",(ctx.user_id,ctx.tenant_id,doc,job,value)).fetchone()[0]
    with ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(claim,[b'a'*32,b'b'*32]))
    assert sum(x is not None for x in results)==1
    with f.db.admin_connection() as c:
        assert c.execute('SELECT state,lease_epoch FROM rag.jobs WHERE job_id=%s',(job,)).fetchone()==('running',initial_epoch+1)
        assert c.execute('SELECT count(*) FROM security.job_authorizations WHERE job_id=%s',(job,)).fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==0
