from uuid import uuid4,UUID
import pytest
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage
from app.errors import AppError

@pytest.fixture
def ingest(db_fixture,tmp_path):
    f=db_fixture
    return f,DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)

def metadata(**changes):
    value={'client_upload_id':uuid4(),'title':'합성 시험','media_type':'text/plain','visibility':'org','reader_ids':[]}
    value.update(changes);return value

RAW='여신심사의 담당 부서는 가상 심사팀이다.'.encode()

def test_same_upload_reuses_exact_receipt(ingest):
    f,r=ingest;ctx=f.run(f.context('A-ADM','A'));m=metadata()
    first=f.run(r.register(ctx,m,RAW));again=f.run(r.register(ctx,m,RAW))
    assert first['job_id']==again['job_id'] and again['replayed']
    with f.db.admin_connection() as c:
        assert c.execute('SELECT count(*) FROM rag.document_versions').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM rag.jobs').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==0
    assert f.run(r.job(ctx,UUID(first['job_id'])))['state']=='queued'

def test_same_id_other_source_rejected(ingest):
    f,r=ingest;ctx=f.run(f.context('A-ADM','A'));m=metadata();f.run(r.register(ctx,m,RAW))
    with pytest.raises(AppError) as e:f.run(r.register(ctx,m,RAW+b'other'))
    assert e.value.status==409

@pytest.mark.parametrize('actor,tenant',[('A-U1','A'),('B-U1','B')])
def test_user_cannot_register_or_write_source(ingest,actor,tenant):
    f,r=ingest;ctx=f.run(f.context(actor,tenant))
    with pytest.raises(AppError) as e:f.run(r.register(ctx,metadata(),RAW))
    assert e.value.status==403 and not list(r.storage.root.rglob('source'))

def test_private_management_does_not_grant_content(ingest):
    f,r=ingest;ctx=f.run(f.context('A-ADM','A'));m=metadata(visibility='private',owner_user_id=f.actor_ids['A-U1'])
    result=f.run(r.register(ctx,m,RAW));listing=f.run(r.listing(ctx,'documents',None,20))
    assert 'title' not in listing['items'][0]
    with pytest.raises(AppError) as e:f.run(r.register(ctx,metadata(expected_revision=1),RAW,UUID(result['document_id'])))
    assert e.value.status==404

def test_new_version_cas_and_old_source_preserved(ingest):
    f,r=ingest;ctx=f.run(f.context('A-ADM','A'));result=f.run(r.register(ctx,metadata(),RAW));doc=UUID(result['document_id'])
    second=f.run(r.register(ctx,metadata(expected_revision=1),RAW+' 추가.'.encode(),doc));assert second['version_id']!=result['version_id']
    with pytest.raises(AppError) as e:f.run(r.register(ctx,metadata(expected_revision=1),RAW,doc))
    assert e.value.status==409

def test_audit_failure_keeps_private_file_recoverable(ingest):
    f,r=ingest;ctx=f.run(f.context('A-ADM','A'));m=metadata()
    with f.db.admin_connection() as c:
        c.execute("CREATE FUNCTION ops.test_document_fault() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'fault';END;$$")
        c.execute('CREATE TRIGGER test_document_fault BEFORE INSERT ON ops.audit_events FOR EACH ROW EXECUTE FUNCTION ops.test_document_fault()')
    with pytest.raises(AppError):f.run(r.register(ctx,m,RAW))
    with f.db.admin_connection() as c:
        assert c.execute('SELECT count(*) FROM rag.document_versions').fetchone()[0]==0
        c.execute('DROP TRIGGER test_document_fault ON ops.audit_events')
    assert len(list(r.storage.root.rglob('source')))==1
    assert not f.run(r.register(ctx,m,RAW))['replayed']

def test_current_revoke_blocks_new_job(ingest):
    f,r=ingest;ctx=f.run(f.context('A-ADM','A'));f.mutate_access(ctx,'membership')
    with pytest.raises(AppError):f.run(r.register(ctx,metadata(),RAW))
    assert not list(r.storage.root.rglob('source'))

def test_only_confirmed_old_orphan_is_removed(ingest):
    import os,time
    f,r=ingest;ctx=f.run(f.context('A-ADM','A'));ids=f.run(r.register(ctx,metadata(),RAW))
    orphan_doc,orphan_version=uuid4(),uuid4();stored=r.storage.write(ctx.tenant_id,orphan_doc,orphan_version,RAW,'합성 시험','text/plain')
    assert f.run(r.cleanup_orphans(ctx))==0
    path=r.storage.root/stored.object_key;os.utime(path,(time.time()-120,time.time()-120))
    registered=list(r.storage.root.rglob('source'));assert len(registered)==2
    assert f.run(r.cleanup_orphans(ctx))==1
    assert len(list(r.storage.root.rglob('source')))==1
    assert f.run(r.job(ctx,UUID(ids['job_id'])))['state']=='queued'

def test_document_admission_limit_and_same_id_replay(ingest):
    f,r=ingest;ctx=f.run(f.context('A-ADM','A'));m=metadata();first=f.run(r.register(ctx,m,RAW))
    for _ in range(9):f.run(r.register(ctx,metadata(),RAW))
    assert f.run(r.register(ctx,m,RAW))['job_id']==first['job_id']
    with pytest.raises(AppError) as e:f.run(r.register(ctx,metadata(),RAW))
    assert e.value.status==429 and len(list(r.storage.root.rglob('source')))==10
