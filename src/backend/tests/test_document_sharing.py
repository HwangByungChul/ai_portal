from uuid import UUID,uuid4
from datetime import date
import pytest
from app.documents.sharing import SharingRepository
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage
from app.documents.worker import DocumentWorker
from app.documents.embedding import EmbeddingGateway,MockEmbeddingProvider
from app.db import open_index_pool,open_meter_pool,tenant_transaction
from app.errors import AppError
from test_operations import ops_rows
from test_document_ingest import metadata,RAW

async def publish(f,repo,ctx,meta=None,raw=RAW,document=None):
    ids=await repo.register(ctx,meta or metadata(),raw,document)
    async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
        await DocumentWorker(repo,EmbeddingGateway(index,meter,MockEmbeddingProvider(),date(2026,10,1))).run(ctx,UUID(ids['job_id']))
    return ids

def test_exact_version_grant_current_list_and_revoke(ops_rows,tmp_path):
    f=ops_rows
    async def check():
        a=await f.context('A-ADM','A');b=await f.context('B-U1','B');repo=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40);share=SharingRepository(repo)
        v1=await publish(f,repo,a);doc=UUID(v1['document_id']);version=UUID(v1['version_id'])
        assert (await share.readable(b,None,20))['items']==[]
        listing=await share.control(a,doc,version)
        g=await share.control(a,doc,version,'issue',f.tenant_ids['B'],expected=listing['publication_revision'],request=uuid4())
        duplicate=await share.control(a,doc,version,'issue',f.tenant_ids['B'],expected=listing['publication_revision'],request=uuid4());assert duplicate['replayed'] and g['grant_id']==duplicate['grant_id']
        v2=await publish(f,repo,a,metadata(expected_revision=1),raw='다른 업무의 담당 부서는 다른팀이다.'.encode(),document=doc)
        rows=(await share.readable(b,None,20))['items'];assert [str(x['version_id']) for x in rows]==[v1['version_id']]
        with pytest.raises(AppError):await share.control(await f.context('B-ADM','B'),doc,version,'issue',f.tenant_ids['A'],expected=1,request=uuid4())
        await share.control(a,action='revoke',grant=UUID(g['grant_id']),expected=g['revision'],request=uuid4())
        assert (await share.readable(b,None,20))['items']==[]
        assert (await share.control(a,action='revoke',grant=UUID(g['grant_id']),expected=1,request=uuid4()))['replayed']
        assert len((await share.readable(a,None,20))['items'])==2
    f.run(check())

@pytest.mark.parametrize('case',['private','wrong_revision','user','foreign','inactive_recipient','audit'])
def test_grant_rejects_and_rollback(ops_rows,tmp_path,case):
    f=ops_rows
    async def check():
        a=await f.context('A-ADM','A');repo=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40);share=SharingRepository(repo)
        ids=await publish(f,repo,a,metadata(visibility='private',owner_user_id=f.actor_ids['A-U1']) if case=='private' else None);doc=UUID(ids['document_id']);version=UUID(ids['version_id'])
        ctx=await f.context('A-U1','A') if case=='user' else await f.context('B-ADM','B') if case=='foreign' else a
        if case=='inactive_recipient':
            with f.db.admin_connection() as c:c.execute('UPDATE security.tenants SET active=false WHERE tenant_id=%s',(f.tenant_ids['B'],))
        if case=='audit':
            with f.db.admin_connection() as c:c.execute("CREATE FUNCTION ops.c04_audit_fail() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'fixed fault'; END;$$; CREATE TRIGGER c04_audit_fail BEFORE INSERT ON ops.audit_events FOR EACH ROW EXECUTE FUNCTION ops.c04_audit_fail()")
        with pytest.raises(AppError):await share.control(ctx,doc,version,'issue',f.tenant_ids['B'],expected=99 if case=='wrong_revision' else 1,request=uuid4())
        with f.db.admin_connection() as c:assert c.execute('SELECT count(*) FROM security.share_grants').fetchone()[0]==0
    f.run(check())


def test_concurrent_exact_version_grant_has_one_active_row(ops_rows,tmp_path):
    import asyncio
    f=ops_rows
    async def check():
        a=await f.context('A-ADM','A');repo=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
        ids=await publish(f,repo,a)
        async def issue():
            from app.db import open_web_pool
            async with open_web_pool(f.db.runtime_dsn('ai_web')) as pool:
                sharing=SharingRepository(DocumentRepository(pool,repo.storage,'x'*40))
                return await sharing.control(a,UUID(ids['document_id']),UUID(ids['version_id']),'issue',f.tenant_ids['B'],expected=1,request=uuid4())
        left,right=await asyncio.gather(issue(),issue())
        assert left['grant_id']==right['grant_id'] and sum(x['replayed'] for x in (left,right))==1
        with f.db.admin_connection() as c:assert c.execute('SELECT count(*) FROM security.share_grants WHERE active').fetchone()[0]==1
    f.run(check())
