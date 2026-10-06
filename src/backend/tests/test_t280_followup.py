"""Owned-fixture document failure, cleanup and explicit-retry integration checks."""
import asyncio
from datetime import date
from pathlib import Path
from uuid import UUID,uuid4
import pytest
from app.db import open_index_pool,open_meter_pool
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage
from app.documents.worker import DocumentWorker
from app.documents.embedding import EmbeddingGateway,MockEmbeddingProvider
from app.documents.policy import resolve_readable_version
from test_document_ingest import metadata,RAW
from test_document_sharing import publish
from test_operations import ops_rows,headers
from test_document_api import multipart
from test_auth_restart import WRITE

@pytest.mark.parametrize('order',['index_before_cleanup','cleanup_before_index'])
def test_delete_cleanup_obeys_tenant_queue_and_duplicate_request(ops_rows,auth_settings,tmp_path,monkeypatch,order):
    import httpx
    import app.main as main
    from pydantic import SecretStr
    f=ops_rows
    async def check():
        class Block(MockEmbeddingProvider):
            def __init__(self):self.calls=0;self.block=False;self.entered=asyncio.Event();self.release=asyncio.Event()
            async def embed(self,claim,texts,tokens):
                self.calls+=1
                if self.block:self.entered.set();await self.release.wait()
                return await super().embed(claim,texts,tokens)
        monkeypatch.setattr(main,'MockEmbeddingProvider',Block)
        settings=auth_settings.model_copy(update={'index_enabled':True,'index_dsn':SecretStr(f.db.runtime_dsn('ai_index')),'meter_dsn':SecretStr(f.db.runtime_dsn('ai_meter')),'source_root':tmp_path/'api-sources'})
        app=main.create_app(settings)
        async with app.router.lifespan_context(app):
            manager=app.state.document_manager;provider=manager.worker.gateway.provider;cleanup_entered=asyncio.Event();cleanup_release=asyncio.Event();cleanup_calls=0;original=manager.cleanup
            async def tracked(ctx,doc):
                nonlocal cleanup_calls
                cleanup_calls+=1;cleanup_entered.set()
                if order=='cleanup_before_index':await cleanup_release.wait()
                await original(ctx,doc)
            manager.cleanup=tracked
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',50000)),base_url='http://127.0.0.1:8000') as client:
                    reply=await client.post('/api/v1/auth/login',headers=WRITE,json={'login_id':'a-adm','password':f.passwords['A-ADM']});assert reply.status_code==200;h=headers(f,'A',reply.json()['data']['csrf_token'])
                    reply=await client.post('/api/v1/admin/documents',headers=h,files=multipart({'client_upload_id':str(uuid4()),'title':'정리 대상 합성 문서','media_type':'text/plain'},RAW));assert reply.status_code==202;first=reply.json()['data']
                    await asyncio.wait_for(asyncio.gather(*list(manager.tasks.values())),5)
                    source=app.state.documents.storage.root/f"tenants/{f.tenant_ids['A']}/documents/{first['document_id']}/{first['version_id']}/source";assert source.exists()
                    provider.block=order=='index_before_cleanup'
                    async def upload():
                        response=await client.post('/api/v1/admin/documents',headers=h,files=multipart({'client_upload_id':str(uuid4()),'title':'다음 합성 문서','media_type':'text/plain'},RAW));assert response.status_code==202;return response.json()['data']
                    async def remove():
                        response=await client.request('DELETE','/api/v1/admin/documents/'+first['document_id'],headers=h,json={'expected_revision':1});assert response.status_code==200 and response.json()['data']['access_state']=='deleted'
                    if order=='index_before_cleanup':
                        second=await upload();await asyncio.wait_for(provider.entered.wait(),5);await remove();await remove();await asyncio.sleep(.05)
                        assert not cleanup_entered.is_set() and source.exists()
                    else:
                        await remove();await asyncio.wait_for(cleanup_entered.wait(),5);await remove();second=await upload();await asyncio.sleep(.05)
                        with f.db.admin_connection() as conn:assert conn.execute('SELECT state FROM rag.jobs WHERE job_id=%s',(second['job_id'],)).fetchone()[0]=='queued'
                        assert cleanup_calls==1 and provider.calls==1
                    # Deletion access is already committed even while physical removal waits.
                    with f.db.admin_connection() as conn:
                        assert conn.execute('SELECT deleted_at IS NOT NULL FROM security.document_access WHERE document_id=%s',(first['document_id'],)).fetchone()[0]
                        assert conn.execute('SELECT count(*) FROM security.document_publications WHERE document_id=%s AND active',(first['document_id'],)).fetchone()[0]==0
                        assert conn.execute("SELECT count(*) FROM rag.jobs WHERE document_id=%s AND job_kind='internal_cleanup'",(first['document_id'],)).fetchone()[0]==1
                    provider.release.set();cleanup_release.set();await asyncio.wait_for(asyncio.gather(*list(manager.tasks.values())),10)
                    assert not source.exists() and cleanup_calls==1 and provider.calls==2
                    with f.db.admin_connection() as conn:
                        assert conn.execute("SELECT count(*) FROM rag.jobs WHERE state='completed'").fetchone()[0]==3
                        assert conn.execute("SELECT count(*) FROM ops.call_attempts WHERE state='settled'").fetchone()[0]==2
                        assert conn.execute("SELECT active_slot FROM ops.project_budget WHERE mode='mock'").fetchone()[0]==0
            finally:provider.release.set();cleanup_release.set()
    f.run(check())

@pytest.mark.parametrize('table',['evidence','relations'])
def test_graph_db_write_failure_preserves_old_publication_and_cost(ops_rows,tmp_path,table):
    f=ops_rows
    async def check():
        admin=await f.context('A-ADM','A');user=await f.context('A-U1','A');repo=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
        previous=await publish(f,repo,admin);ids=await repo.register(admin,metadata(expected_revision=1),RAW,UUID(previous['document_id']))
        with f.db.admin_connection() as conn:conn.execute(f'ALTER TABLE rag.{table} ADD CONSTRAINT t280_owned_fault CHECK(false) NOT VALID')
        async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            provider=MockEmbeddingProvider();worker=DocumentWorker(repo,EmbeddingGateway(index,meter,provider,date(2026,10,1)))
            with pytest.raises(Exception):await worker.run(admin,UUID(ids['job_id']))
            view=await repo.job(admin,UUID(ids['job_id']));assert view['state']=='needs_review' and not view['retry_allowed'] and view['safe_error_code']=='INDEX_INTERRUPTED'
            assert (await resolve_readable_version(f.pool,user,UUID(ids['document_id']))).version_id==UUID(previous['version_id'])
            with f.db.admin_connection() as conn:
                for name in ['entities','relations','evidence','relation_evidence']:
                    assert conn.execute(f'SELECT count(*) FROM rag.{name} WHERE index_id=%s',(ids['index_id'],)).fetchone()[0]==0
                assert conn.execute('SELECT count(*) FROM rag.chunks WHERE index_id=%s',(ids['index_id'],)).fetchone()[0]==1
                assert conn.execute('SELECT count(*) FROM security.document_publications WHERE version_id=%s AND active',(ids['version_id'],)).fetchone()[0]==0
                assert conn.execute("SELECT count(*) FROM ops.call_attempts WHERE state='settled'").fetchone()[0]==2
                before=conn.execute("SELECT accounted_krw,reserved_krw,active_slot FROM ops.project_budget WHERE mode='mock'").fetchone();assert before[0]>0 and before[1:]==(0,0)
                conn.execute(f'ALTER TABLE rag.{table} DROP CONSTRAINT t280_owned_fault')
            await worker.run(admin,UUID(ids['job_id']))
            with f.db.admin_connection() as conn:assert conn.execute("SELECT accounted_krw,reserved_krw,active_slot FROM ops.project_budget WHERE mode='mock'").fetchone()==before
    f.run(check())

@pytest.mark.parametrize('state',['failed','needs_review'])
def test_explicit_job_retry_api_same_id_preserves_failure(ops_rows,client,login,state):
    from app.types import AuthContext
    from concurrent.futures import ThreadPoolExecutor
    f=ops_rows;session=login(client,'A-ADM');h=headers(f,'A',session['csrf_token'])
    reply=client.post('/api/v1/admin/documents',headers=h,files=multipart({'client_upload_id':str(uuid4()),'title':'재처리 합성 문서','media_type':'text/plain'},RAW));assert reply.status_code==202;ids=reply.json()['data'];job=UUID(ids['job_id'])
    with f.db.admin_connection() as conn:origin=conn.execute('SELECT origin_session_id FROM rag.jobs WHERE job_id=%s',(job,)).fetchone()[0]
    ctx=AuthContext(origin,f.actor_ids['A-ADM'],f.tenant_ids['A'],'TADMIN','');repo=DocumentRepository(f.pool,client.app.state.documents.storage,'x'*40);claim=b'r'*32
    # Exercise the existing scoped worker failure capability, not a SQL state rewrite.
    owned=f.run(repo.job(ctx,job,'claim',claim=claim));f.run(repo.job(ctx,job,'fail' if state=='failed' else 'review',owned['epoch'],claim,{'code':'INDEX_INTERRUPTED'}))
    view=client.get('/api/v1/admin/jobs/'+str(job),headers=headers(f)).json()['data'];body={'expected_revision':view['revision'],'client_retry_id':str(uuid4())}
    def retry():return client.post('/api/v1/admin/jobs/'+str(job)+'/retry',headers=h,json=body)
    with ThreadPoolExecutor(max_workers=2) as ex:responses=list(ex.map(lambda _:retry(),range(2)))
    if state=='needs_review':
        assert not view['retry_allowed'] and all(x.status_code==409 for x in responses)
        with f.db.admin_connection() as conn:
            assert conn.execute('SELECT count(*) FROM rag.jobs').fetchone()[0]==1
            assert conn.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==0
        return
    assert view['retry_allowed'] and all(x.status_code==202 for x in responses)
    child={x.json()['data']['job_id'] for x in responses};assert len(child)==1;child=child.pop();assert child!=str(job)
    assert sorted(x.json()['data']['replayed'] for x in responses)==[False,True]
    assert client.post('/api/v1/admin/jobs/'+str(job)+'/retry',headers=h,json={**body,'expected_revision':body['expected_revision']+1}).status_code==409
    async def finish():
        async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            await DocumentWorker(repo,EmbeddingGateway(index,meter,MockEmbeddingProvider(),date(2026,10,1))).run(ctx,UUID(child))
    f.run(finish());assert retry().json()['data']['job_id']==child
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT state FROM rag.jobs WHERE job_id=%s',(job,)).fetchone()[0]=='failed'
        assert conn.execute('SELECT state,retry_of,attempt FROM rag.jobs WHERE job_id=%s',(child,)).fetchone()==('completed',job,2)
        assert conn.execute('SELECT count(*) FROM rag.jobs').fetchone()[0]==2
        assert conn.execute('SELECT count(*) FROM rag.index_builds').fetchone()[0]==1
        assert conn.execute("SELECT count(*) FROM security.operation_receipts WHERE operation_kind='retry'").fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==1


def test_native_cleanup_path_failure_restart_keeps_access_closed(ops_rows,auth_settings,tmp_path):
    import time,httpx
    from test_auth_restart import LiveServer,BASE_URL
    f=ops_rows;server=LiveServer(f,auth_settings);root=tmp_path/'native-sources';fault_dir=None
    server.env.update(AI_SOURCE_ROOT=str(root),AI_INDEX_ENABLED='true',AI_EXECUTION_ENABLED='true',AI_INDEX_DSN=f.db.runtime_dsn('ai_index'),AI_METER_DSN=f.db.runtime_dsn('ai_meter'))
    server.secrets += [server.env['AI_INDEX_DSN'],server.env['AI_METER_DSN']]
    def terminal(client,path,h):
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            reply=client.get(path,headers=h);assert reply.status_code==200;view=reply.json()['data']
            if view.get('state') in ('completed','failed','needs_review'):return view
            time.sleep(.05)
        raise AssertionError('T282_TERMINAL_TIMEOUT')
    try:
        server.start()
        with httpx.Client(base_url=BASE_URL,timeout=5,trust_env=False) as client:
            csrf=server.login(client,'A-ADM');h=headers(f,'A',csrf);read=headers(f)
            def upload(title,raw):
                reply=client.post('/api/v1/admin/documents',headers=h,files=multipart({'client_upload_id':str(uuid4()),'title':title,'media_type':'text/plain'},raw));assert reply.status_code==202;ids=reply.json()['data'];assert terminal(client,'/api/v1/admin/jobs/'+ids['job_id'],read)['state']=='completed';return ids
            first=upload('삭제 보호 표식 문서',RAW);other=upload('동명 개체 보존 문서','여신심사의 담당 부서는 기록팀이다.'.encode())
            request={'client_send_id':str(uuid4()),'agent_key':'rules_rag','prompt':'여신심사 담당 부서는?','document_refs':[{'document_id':first['document_id'],'version_id':first['version_id']}]}
            reply=client.post('/api/v1/runs',headers=h,json=request);assert reply.status_code==202;run=reply.json()['data']['run_id'];assert terminal(client,'/api/v1/runs/'+run,read)['state']=='completed'
            item=client.get('/api/v1/runs/'+run+'/evidence',headers=read).json()['data']['items'][0];assert client.get(item['source_url'],headers=read).content==RAW
            path=root/f"tenants/{f.tenant_ids['A']}/documents/{first['document_id']}/{first['version_id']}/source";fault_dir=path.parent;fault_dir.chmod(0o500)
            reply=client.request('DELETE','/api/v1/admin/documents/'+first['document_id'],headers=h,json={'expected_revision':1});assert reply.status_code==200 and reply.json()['data']['cleanup_state']=='pending'
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                with f.db.admin_connection() as conn:purged=conn.execute('SELECT payload_purged FROM rag.document_versions WHERE version_id=%s',(first['version_id'],)).fetchone()[0]
                if purged:break
                time.sleep(.05)
            assert purged and path.exists()
            with f.db.admin_connection() as conn:
                assert conn.execute("SELECT state FROM rag.jobs WHERE document_id=%s AND job_kind='internal_cleanup'",(first['document_id'],)).fetchone()[0]=='queued'
                before=conn.execute("SELECT (SELECT count(*) FROM ops.call_attempts),accounted_krw,reserved_krw,active_slot FROM ops.project_budget WHERE mode='mock'").fetchone();assert before[0]==4 and before[2:]==(0,0)
                assert conn.execute('SELECT count(*) FROM rag.relations WHERE document_id=%s AND NOT payload_purged',(other['document_id'],)).fetchone()[0]==1
            view=client.get('/api/v1/runs/'+run,headers=read).json()['data'];assert view['content_status']=='unavailable' and view['result'] is None
            assert client.get(item['source_url'],headers=read).status_code==404
            assert client.post('/api/v1/runs',headers=h,json={**request,'client_send_id':str(uuid4())}).status_code==404
            assert first['document_id'] not in {x['document_id'] for x in client.get('/api/v1/documents',headers=read).json()['data']['items']}
            fault_dir.chmod(0o700);server.restart()
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                with f.db.admin_connection() as conn:done=conn.execute("SELECT state FROM rag.jobs WHERE document_id=%s AND job_kind='internal_cleanup'",(first['document_id'],)).fetchone()[0]
                if done=='completed':break
                time.sleep(.05)
            assert done=='completed' and not path.exists()
            assert client.get(item['source_url'],headers=read).status_code==404 and client.get('/api/v1/runs/'+run,headers=read).json()['data']['result'] is None
            assert other['document_id'] in {x['document_id'] for x in client.get('/api/v1/documents',headers=read).json()['data']['items']}
            with f.db.admin_connection() as conn:
                assert conn.execute("SELECT (SELECT count(*) FROM ops.call_attempts),accounted_krw,reserved_krw,active_slot FROM ops.project_budget WHERE mode='mock'").fetchone()==before
                assert conn.execute('SELECT count(*) FROM rag.relations WHERE document_id=%s AND NOT payload_purged',(other['document_id'],)).fetchone()[0]==1
        server.log.flush();content=server.log_path.read_text();assert not any(x and x in content for x in server.secrets)
    finally:
        if fault_dir is not None:fault_dir.chmod(0o700)
        server.stop();server.log.close()
