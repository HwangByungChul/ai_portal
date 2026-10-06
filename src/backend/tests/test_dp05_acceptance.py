from uuid import uuid4,UUID
from datetime import date
import json
import pytest
import psycopg
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage
from app.documents.worker import DocumentWorker
from app.documents.manager import DocumentManager
from app.documents.embedding import EmbeddingGateway
from app.documents.policy import resolve_readable_version,DocumentUnavailable
from app.documents.sharing import SharingRepository
from app.db import open_index_pool,open_meter_pool,tenant_transaction
from app.errors import AppError
from test_operations import ops_rows,headers
from test_document_api import multipart
from test_document_jobs import CountingEmbedding
from test_document_ingest import RAW,metadata
from test_rag_execution import execute


def meta(**changes):
    result={'client_upload_id':uuid4(),'title':'개인 합성 자료','media_type':'text/plain'}
    result.update(changes);return result

def httpmeta(**changes):return {k:str(v) if isinstance(v,UUID) else v for k,v in meta(**changes).items()}

@pytest.fixture
def personal(ops_rows,tmp_path):
    return ops_rows,DocumentRepository(ops_rows.pool,SourceStorage(tmp_path/'sources'),'x'*40)

async def ready(f,repo,ctx,ids,provider=None):
    async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
        await DocumentWorker(repo,EmbeddingGateway(index,meter,provider or CountingEmbedding(),date(2026,10,1))).run(ctx,UUID(ids['job_id']))


def test_user_upload_endpoint_replay_changed_and_audit(client,login,db_fixture):
    f=db_fixture;auth=login(client,'A-U1');h=headers(f,csrf=auth['csrf_token']);m=httpmeta()
    reply=client.post('/api/v1/documents',headers=h,files=multipart(m,RAW));assert reply.status_code==202
    ids=reply.json()['data'];same=client.post('/api/v1/documents',headers=h,files=multipart(m,RAW));assert same.status_code==202 and same.json()['data']['job_id']==ids['job_id'] and same.json()['data']['replayed']
    assert client.post('/api/v1/documents',headers=h,files=multipart(m,RAW+b'changed')).status_code==409
    rows=client.get('/api/v1/documents/mine',headers=h).json()['data']['items'];assert len(rows)==1 and rows[0]['title']==m['title'] and rows[0]['visibility']=='private'
    assert client.get('/api/v1/document-jobs/'+ids['job_id'],headers=h).json()['data']['retry_allowed'] is False
    with f.db.admin_connection() as c:
        assert c.execute('SELECT owner_user_id,user_owned,visibility FROM security.document_access').fetchone()==(f.actor_ids['A-U1'],True,'private')
        assert c.execute('SELECT count(*) FROM rag.jobs').fetchone()==(1,)
        assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()==(0,)
        trace=c.execute('SELECT revisions FROM ops.audit_events WHERE event_id=%s',(reply.headers['x-request-id'],)).fetchone()[0];assert trace=={'job_ids':[ids['job_id']]}
        assert m['title'] not in repr(c.execute("SELECT revisions FROM ops.audit_events WHERE action LIKE 'document.%'").fetchall())

@pytest.mark.parametrize('case',['owner_user_id','visibility','reader_ids','tenant_id','source_url','expected_revision','extra','csrf','origin','duplicate','media','big','utf8','characters'])
def test_invalid_upload_never_writes_or_dispatches(client,login,db_fixture,case):
    f=db_fixture;csrf=login(client,'A-U1')['csrf_token'];h=headers(f,csrf=csrf);m=httpmeta();raw=RAW
    if case in ['owner_user_id','tenant_id']:m[case]=str(uuid4())
    elif case=='visibility':m[case]='org'
    elif case=='reader_ids':m[case]=[str(f.actor_ids['A-U2'])]
    elif case=='source_url':m[case]='https://example.invalid/private'
    elif case=='expected_revision':m[case]=1
    elif case=='extra':m[case]='bad'
    elif case=='csrf':h.pop('X-CSRF-Token')
    elif case=='origin':h['Origin']='https://example.invalid'
    elif case=='media':m['media_type']='application/pdf'
    elif case=='big':raw=b'x'*147456
    elif case=='utf8':raw=b'\xff\xfe'
    elif case=='characters':raw=b'a'*40001
    parts=multipart(m,raw)
    if case=='duplicate':parts.append(('metadata',(None,json.dumps(m))))
    assert client.post('/api/v1/documents',headers=h,files=parts).status_code in (403,413,422)
    with f.db.admin_connection() as c:assert c.execute('SELECT (SELECT count(*) FROM rag.jobs),(SELECT count(*) FROM ops.call_attempts)').fetchone()==(0,0)
    assert not list(client.app.state.documents.storage.root.rglob('source'))

@pytest.mark.parametrize('actor,tenant',[('A-U2','A'),('B-U1','B'),('A-ADM','A'),('P-A','A')])
def test_foreign_users_admins_private_readers_cannot_manage(client,login,ops_rows,actor,tenant):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];h=headers(f,csrf=csrf)
    ids=client.post('/api/v1/documents',headers=h,files=multipart(httpmeta(),RAW)).json()['data']
    csrf=login(client,actor)['csrf_token'];h=headers(f,tenant,csrf)
    assert client.get('/api/v1/documents/mine',headers=h).json()['data']['items']==[]
    assert client.get('/api/v1/document-jobs',headers=h).json()['data']['items']==[]
    assert client.get('/api/v1/document-jobs/'+ids['job_id'],headers=h).status_code==404
    assert client.request('DELETE','/api/v1/documents/'+ids['document_id'],headers=h,json={'expected_revision':1}).status_code==404
    assert client.get('/api/v1/documents',headers=h).json()['data']['items']==[]
    body={'agent_key':'rules_rag','client_send_id':str(uuid4()),'prompt':'질문','document_refs':[{'document_id':ids['document_id'],'version_id':ids['version_id']}]}
    with f.db.admin_connection() as c:c.execute("UPDATE portal.agent_configs SET enabled=true WHERE agent_key='rules_rag'")
    assert client.post('/api/v1/runs',headers=h,json=body).status_code==404


def test_cursor_bounds_actor_kind_and_unknown_query(client,login,db_fixture):
    f=db_fixture;csrf=login(client,'A-U1')['csrf_token'];h=headers(f,csrf=csrf)
    for _ in range(2):assert client.post('/api/v1/documents',headers=h,files=multipart(httpmeta(),RAW)).status_code==202
    cursor=client.get('/api/v1/documents/mine?limit=1',headers=h).json()['data']['next_cursor'];assert cursor
    assert len(client.get('/api/v1/documents/mine',headers=h,params={'cursor':cursor}).json()['data']['items'])==1
    assert client.get('/api/v1/document-jobs',headers=h,params={'cursor':cursor}).status_code==422
    assert client.get('/api/v1/documents/mine?limit=1&limit=2',headers=h).status_code==422
    assert client.get('/api/v1/documents/mine?owner_user_id=x',headers=h).status_code==422
    login(client,'A-U2');assert client.get('/api/v1/documents/mine',headers=h,params={'cursor':cursor}).status_code==422


def test_unpublished_refs_block_then_owner_publishes_deletes_cleanup_and_hides_feedback(personal):
    from app.feedback.repository import FeedbackRepository
    f,repo=personal
    async def check():
        ctx=await f.context('A-U1','A');ids=await repo.register(ctx,meta(),RAW,personal=True,request_id=uuid4());doc,version=UUID(ids['document_id']),UUID(ids['version_id']);refs=[{'document_id':doc,'version_id':version}]
        with pytest.raises(AppError) as e:await execute(f,repo,ctx,refs=refs)
        assert e.value.status==404
        provider=CountingEmbedding();await ready(f,repo,ctx,ids,provider);await ready(f,repo,ctx,ids,provider);assert provider.calls==1
        assert (await repo.personal_job(ctx,UUID(ids['job_id'])))['state']=='completed'
        assert (await resolve_readable_version(f.pool,ctx,doc,version)).document_id==doc
        for actor,tenant in [('A-U2','A'),('B-U1','B'),('A-ADM','A')]:
            with pytest.raises(DocumentUnavailable):await resolve_readable_version(f.pool,await f.context(actor,tenant),doc,version)
        admitted,result,ticket=await execute(f,repo,ctx,refs=refs);assert result.answer_kind=='answer' and '[1]' in result.body
        feedback=FeedbackRepository(f.pool);await feedback.mutate(ctx,ticket.run.run_id,{'rating':'positive','comment':'내 비공개 자료 평가'},0,False,uuid4())
        with f.db.admin_connection() as c:before=c.execute('SELECT call_id,state,price_snapshot,usage_snapshot FROM ops.call_attempts ORDER BY call_id').fetchall()
        with pytest.raises(AppError) as e:await repo.delete(ctx,doc,9,personal=True)
        assert e.value.status==409
        await repo.delete(ctx,doc,1,uuid4(),personal=True)
        with pytest.raises(DocumentUnavailable):await resolve_readable_version(f.pool,ctx,doc,version)
        with pytest.raises(AppError):await execute(f,repo,ctx,refs=refs)
        with pytest.raises(AppError) as e:await feedback.read(ctx,ticket.run.run_id,b'x'*32)
        assert e.value.code=='FEEDBACK_NOT_READY'
        async with tenant_transaction(f.pool,ctx) as c:
            assert await (await c.execute("SELECT body FROM portal.messages WHERE run_id=%s AND role='assistant'",(ticket.run.run_id,))).fetchone() is None
            view=(await (await c.execute("SELECT security.run_read(%s,%s,'run',%s,NULL,20) AS data",(ctx.session_id,ctx.tenant_id,ticket.run.run_id))).fetchone())['data'];assert view['state']=='completed' and view['result'] is None
            assert await (await c.execute('SELECT * FROM portal.answer_evidence')).fetchall()==[]
        async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            worker=DocumentWorker(repo,EmbeddingGateway(index,meter,provider,date(2026,10,1)))
            manager=DocumentManager(worker,'mock');await manager.cleanup(ctx,doc)
        assert not list(repo.storage.root.rglob('source'))
        with f.db.admin_connection() as c:
            assert c.execute('SELECT call_id,state,price_snapshot,usage_snapshot FROM ops.call_attempts ORDER BY call_id').fetchall()==before
            assert c.execute('SELECT provenance_sealed,source_count FROM portal.runs WHERE run_id=%s',(ticket.run.run_id,)).fetchone()==(True,1)
            assert c.execute('SELECT title,source_object_key,payload_purged FROM rag.document_versions WHERE document_id=%s',(doc,)).fetchone()==(None,None,True)
            assert c.execute("SELECT state FROM rag.jobs WHERE document_id=%s AND job_kind='internal_cleanup'",(doc,)).fetchone()==('completed',)
    f.run(check())

@pytest.mark.parametrize('mutation',['membership','account','tenant','revoked','expired','agent'])
def test_saved_personal_job_rechecks_current_principal_not_http_lifetime(personal,mutation):
    f,repo=personal
    async def check():
        ctx=await f.context('A-U1','A');ids=await repo.register(ctx,meta(),RAW,personal=True);provider=CountingEmbedding()
        if mutation=='agent':
            with f.db.admin_connection() as c:c.execute("UPDATE portal.agent_configs SET enabled=false WHERE tenant_id=%s AND agent_key='rules_rag'",(ctx.tenant_id,))
        else:f.mutate_access(ctx,mutation)
        if mutation in ('revoked','expired'):
            await ready(f,repo,ctx,ids,provider);assert provider.calls==1
        else:
            with pytest.raises(Exception):await ready(f,repo,ctx,ids,provider)
            assert provider.calls==0
            with f.role_connection('ai_web') as c:c.execute("SELECT security.document_pending('mock')")
            with f.db.admin_connection() as c:
                if mutation!='agent':assert c.execute('SELECT state FROM rag.jobs WHERE job_id=%s',(ids['job_id'],)).fetchone()==('blocked',)
    f.run(check())


def test_user_controls_cannot_manage_admin_private_doc_or_org_and_delete_replay(personal):
    f,repo=personal
    async def check():
        owner=await f.context('A-U1','A');admin=await f.context('A-ADM','A');oldmeta=metadata(visibility='private',owner_user_id=owner.user_id,reader_ids=[f.actor_ids['A-U2']]);legacy=await repo.register(admin,oldmeta,RAW)
        assert (await repo.personal_listing(owner,'documents',None,20))['items']==[]
        with pytest.raises(AppError):await repo.delete(owner,UUID(legacy['document_id']),1,personal=True)
        with pytest.raises(AppError):await repo.personal_job(owner,UUID(legacy['job_id']))
        org=await repo.register(admin,metadata(),RAW)
        with pytest.raises(AppError):await repo.delete(owner,UUID(org['document_id']),1,personal=True)
        m=meta();mine=await repo.register(owner,m,RAW,personal=True)
        await repo.delete(owner,UUID(mine['document_id']),1,personal=True)
        assert (await repo.delete(owner,UUID(mine['document_id']),1,personal=True))['access_state']=='deleted'
        with pytest.raises(AppError) as e:await repo.register(owner,m,RAW,personal=True)
        assert e.value.status==409
        with f.db.admin_connection() as c:
            assert c.execute('SELECT count(*) FROM security.document_access WHERE NOT user_owned AND deleted_at IS NULL').fetchone()==(2,)
            assert c.execute("SELECT count(*) FROM rag.jobs WHERE job_kind='internal_cleanup'").fetchone()==(1,)
    f.run(check())


def test_marker_immutable_raw_write_and_admin_job_control_denied(personal):
    f,repo=personal
    async def check():
        ctx=await f.context('A-U1','A');ids=await repo.register(ctx,meta(),RAW,personal=True)
        with pytest.raises(AppError) as e:await repo.job(ctx,UUID(ids['job_id']),'claim',claim=b'x'*32)
        assert e.value.status==403
        with pytest.raises(AppError):await repo.cleanup_orphans(ctx)
        async with tenant_transaction(f.pool,ctx) as c:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):await c.execute('UPDATE security.document_access SET user_owned=false')
        with f.db.admin_connection() as c:
            with pytest.raises(psycopg.errors.CheckViolation):c.execute('UPDATE security.document_access SET user_owned=false WHERE document_id=%s',(ids['document_id'],))
        f.verify_catalog()
    f.run(check())


def test_personal_admission_rate_limit_replay_and_admin_receipt_not_reused(personal):
    f,repo=personal
    async def check():
        ctx=await f.context('A-U1','A');m=meta();ids=await repo.register(ctx,m,RAW,personal=True)
        for _ in range(9):await repo.register(ctx,meta(),RAW,personal=True)
        assert (await repo.register(ctx,m,RAW,personal=True))['job_id']==ids['job_id']
        with pytest.raises(AppError) as e:await repo.register(ctx,meta(),RAW,personal=True)
        assert e.value.status==429 and len(list(repo.storage.root.rglob('source')))==10
        admin=await f.context('A-ADM','A');m=meta();await repo.register(admin,{**m,'visibility':'private','owner_user_id':admin.user_id,'reader_ids':[]},RAW)
        with pytest.raises(AppError) as e:await repo.register(admin,m,RAW,personal=True)
        assert e.value.status==409
    f.run(check())

@pytest.mark.parametrize('mutation',['membership','agent'])
def test_personal_revocation_after_embedding_prevents_publication_and_preserves_charge(personal,mutation):
    f,repo=personal
    class Revoking(CountingEmbedding):
        async def embed(self,claim,texts,tokens):
            out=await super().embed(claim,texts,tokens)
            with f.db.admin_connection() as c:
                if mutation=='membership':c.execute('UPDATE security.memberships SET active=false WHERE tenant_id=%s AND user_id=%s',(f.tenant_ids['A'],f.actor_ids['A-U1']))
                else:c.execute("UPDATE portal.agent_configs SET enabled=false WHERE tenant_id=%s AND agent_key='rules_rag'",(f.tenant_ids['A'],))
            return out
    async def check():
        ctx=await f.context('A-U1','A');ids=await repo.register(ctx,meta(),RAW,personal=True);provider=Revoking()
        with pytest.raises(Exception):await ready(f,repo,ctx,ids,provider)
        assert provider.calls==1
        with f.db.admin_connection() as c:
            assert c.execute('SELECT count(*) FROM security.document_publications WHERE active').fetchone()==(0,)
            assert c.execute('SELECT state FROM ops.call_attempts').fetchone()==('settled',)
    f.run(check())


def test_personal_cleanup_rejects_foreign_actor_and_revoked_membership_then_recovers(personal):
    f,repo=personal
    async def check():
        ctx=await f.context('A-U1','A');other=await f.context('A-U2','A');ids=await repo.register(ctx,meta(),RAW,personal=True);doc=UUID(ids['document_id']);await repo.delete(ctx,doc,1,personal=True)
        async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            manager=DocumentManager(DocumentWorker(repo,EmbeddingGateway(index,meter,CountingEmbedding(),date(2026,10,1))),'mock')
            with pytest.raises(Exception):await manager.cleanup(other,doc)
            f.mutate_access(ctx,'membership')
            with pytest.raises(Exception):await manager.cleanup(ctx,doc)
            assert len(list(repo.storage.root.rglob('source')))==1
            with f.db.admin_connection() as c:c.execute('UPDATE security.memberships SET active=true WHERE tenant_id=%s AND user_id=%s',(ctx.tenant_id,ctx.user_id))
            await manager.cleanup(ctx,doc)
            assert not list(repo.storage.root.rglob('source'))
    f.run(check())


def test_personal_audit_rollback_keeps_file_recoverable_and_no_receipt(personal):
    f,repo=personal
    async def check():
        ctx=await f.context('A-U1','A');m=meta()
        with f.db.admin_connection() as c:c.execute("ALTER TABLE ops.audit_events ADD CONSTRAINT dp05_fault CHECK(action<>'document.upload')")
        with pytest.raises(AppError):await repo.register(ctx,m,RAW,personal=True)
        with f.db.admin_connection() as c:
            assert c.execute('SELECT (SELECT count(*) FROM rag.jobs),(SELECT count(*) FROM security.operation_receipts)').fetchone()==(0,0)
            c.execute('ALTER TABLE ops.audit_events DROP CONSTRAINT dp05_fault')
        assert len(list(repo.storage.root.rglob('source')))==1
        assert (await repo.register(ctx,m,RAW,personal=True))['replayed'] is False
    f.run(check())


def test_personal_queued_recovery_retains_only_admitted_owner_job(personal):
    f,repo=personal
    async def check():
        ctx=await f.context('A-U1','A');admin=await f.context('A-ADM','A');mine=await repo.register(ctx,meta(),RAW,personal=True);legacy=await repo.register(admin,metadata(),RAW)
        with f.db.admin_connection() as c:c.execute("UPDATE security.memberships SET role='USER',revision=revision+1 WHERE tenant_id=%s AND user_id=%s",(admin.tenant_id,admin.user_id))
        f.mutate_access(ctx,'revoked')
        with f.role_connection('ai_web') as c:pending=c.execute("SELECT security.document_pending('mock')").fetchone()[0]
        assert [x['job_id'] for x in pending]==[mine['job_id']]
        with f.db.admin_connection() as c:assert c.execute('SELECT state FROM rag.jobs WHERE job_id=%s',(legacy['job_id'],)).fetchone()==('blocked',)
        provider=CountingEmbedding();await ready(f,repo,ctx,mine,provider);assert provider.calls==1
    f.run(check())
