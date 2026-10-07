import asyncio,copy,hashlib
from dataclasses import replace
from uuid import UUID,uuid4
from pathlib import Path
import pytest
from app.documents.storage import StoredSource,SourceStorageError
from app.documents.formats import DOCX_MEDIA_TYPE
from app.documents.repository import DocumentRepository
from app.db import open_web_pool
from app.errors import AppError
from docx_support import docx_bytes,p,table
from test_document_ingest import ingest,metadata,RAW
from test_operations import ops_rows

def meta(personal):
 m=metadata(media_type=DOCX_MEDIA_TYPE)
 return {k:m[k] for k in ('client_upload_id','title','media_type')} if personal else m

def stored(f):
 with f.db.admin_connection() as c:row=c.execute('SELECT source_object_key,source_sha256,byte_length,character_length,title,media_type,source_mapping FROM rag.document_versions').fetchone()
 return StoredSource(row[0],bytes(row[1]),*row[2:])

@pytest.mark.parametrize('personal',[False,True])
def test_docx_hash_locations_and_replay_without_parser(ingest,monkeypatch,personal):
 f,r=ingest;ctx=f.run(f.context('A-U1' if personal else 'A-ADM','A'));m=meta(personal);raw=docx_bytes(p('합성 안내')+table([[RAW.decode()]]))
 ids=f.run(r.register(ctx,m,raw,personal=personal));source=stored(f)
 assert r.storage.read(source)=='합성 안내\n\n'.encode()+RAW and r.storage.read_original(source)==raw
 origin=source.source_mapping['origin'];assert origin['source_sha256']==hashlib.sha256(raw).hexdigest() and origin['text_sha256']==source.sha256.hex()
 assert origin['locations'][1]['kind']=='table_cell'
 import app.documents.repository as module
 monkeypatch.setattr(module,'extract_docx',lambda _:pytest.fail('confirmed replay must not parse'))
 again=f.run(r.register(ctx,m,raw,personal=personal));assert again['replayed'] and again['job_id']==ids['job_id']
 with f.db.admin_connection() as c:assert c.execute('SELECT count(*) FROM rag.jobs').fetchone()==(1,)

@pytest.mark.parametrize('personal',[False,True])
def test_denied_principal_never_parses_docx(ingest,monkeypatch,personal):
 f,r=ingest;ctx=f.run(f.context('A-U1' if personal else 'A-ADM','A'));f.mutate_access(ctx,'membership')
 import app.documents.repository as module
 monkeypatch.setattr(module,'extract_docx',lambda _:pytest.fail('unauthorized parse'))
 with pytest.raises(AppError):f.run(r.register(ctx,meta(personal),docx_bytes(),personal=personal))
 assert not list(r.storage.root.rglob('source'))

@pytest.mark.parametrize('place',['title','paragraph','table'])
def test_docx_policy_blocks_before_source_job_and_call(ingest,place):
 f,r=ingest;ctx=f.run(f.context('A-ADM','A'));m=meta(False);body=p('safe')
 if place=='title':m['title']='sample@example.invalid'
 elif place=='paragraph':body=p('sample@example.invalid')
 else:body=table([['sample@example.invalid']])
 with pytest.raises(AppError) as e:f.run(r.register(ctx,m,docx_bytes(body)))
 assert e.value.code=='DOCUMENT_POLICY_BLOCKED' and not list(r.storage.root.rglob('source'))
 with f.db.admin_connection() as c:
  assert c.execute('SELECT count(*) FROM rag.jobs').fetchone()==(0,)
  assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()==(0,)

@pytest.mark.parametrize('personal',[False,True])
def test_audit_failure_retains_private_pair_and_same_id_recovers(ingest,personal):
 f,r=ingest;ctx=f.run(f.context('A-U1' if personal else 'A-ADM','A'));m=meta(personal);raw=docx_bytes()
 with f.db.admin_connection() as c:
  c.execute("CREATE FUNCTION ops.dx_fault() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'fixed fault';END;$$")
  c.execute('CREATE TRIGGER dx_fault BEFORE INSERT ON ops.audit_events FOR EACH ROW EXECUTE FUNCTION ops.dx_fault()')
 with pytest.raises(AppError):f.run(r.register(ctx,m,raw,personal=personal))
 assert len(list(r.storage.root.rglob('source')))==1 and len(list(r.storage.root.rglob('original')))==1
 assert all(x.stat().st_mode&0o777==0o600 for x in r.storage.root.rglob('*') if x.is_file())
 with f.db.admin_connection() as c:
  assert c.execute('SELECT count(*) FROM rag.jobs').fetchone()==(0,)
  c.execute('DROP TRIGGER dx_fault ON ops.audit_events')
 ids=f.run(r.register(ctx,m,raw,personal=personal));assert not ids['replayed'] and r.storage.read_original(stored(f))==raw

@pytest.mark.parametrize('personal',[False,True])
def test_revocation_during_parser_blocks_final_storage(ingest,monkeypatch,personal):
 f,r=ingest;ctx=f.run(f.context('A-U1' if personal else 'A-ADM','A'))
 import app.documents.repository as module
 original=module.extract_docx
 def revoke(raw):
  parsed=original(raw);f.mutate_access(ctx,'membership');return parsed
 monkeypatch.setattr(module,'extract_docx',revoke)
 with pytest.raises(AppError):f.run(r.register(ctx,meta(personal),docx_bytes(),personal=personal))
 assert not list(r.storage.root.rglob('source')) and not list(r.storage.root.rglob('original'))

@pytest.mark.parametrize('attack',['corrupt_original','missing_original','location','hash'])
def test_original_and_location_integrity_fails_closed(ingest,attack):
 f,r=ingest;ctx=f.run(f.context('A-ADM','A'));f.run(r.register(ctx,meta(False),docx_bytes()));source=stored(f)
 original=(r.storage.root/source.object_key).with_name('original')
 if attack=='corrupt_original':original.write_bytes(b'corrupted')
 elif attack=='missing_original':original.unlink()
 else:
  mapping=copy.deepcopy(source.source_mapping)
  if attack=='hash':mapping['origin']['text_sha256']='0'*64
  else:mapping['origin']['locations'][0]['start']=1
  source=replace(source,source_mapping=mapping)
 with pytest.raises(SourceStorageError):r.storage.read(source)
 assert r.storage.remove(source.object_key)==1
 assert not original.exists() and not (r.storage.root/source.object_key).exists()

@pytest.mark.parametrize('personal',[False,True])
def test_concurrent_docx_registration_has_single_pair_job(ingest,personal):
 f,r=ingest;ctx=f.run(f.context('A-U1' if personal else 'A-ADM','A'));m=meta(personal);raw=docx_bytes()
 async def check():
  async def upload():
   async with open_web_pool(f.db.runtime_dsn('ai_web')) as pool:
    return await DocumentRepository(pool,r.storage,'x'*40).register(ctx,m,raw,personal=personal)
  left,right=await asyncio.gather(upload(),upload());assert left['job_id']==right['job_id']
 f.run(check())
 with f.db.admin_connection() as c:assert c.execute('SELECT count(*) FROM rag.jobs').fetchone()==(1,)
 assert len(list(r.storage.root.rglob('source')))==1 and len(list(r.storage.root.rglob('original')))==1

def test_docx_exact_version_share_and_revoke(ops_rows,tmp_path):
 from app.documents.sharing import SharingRepository
 from test_document_sharing import publish
 from app.documents.storage import SourceStorage
 f=ops_rows;r=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
 async def check():
  a=await f.context('A-ADM','A');b=await f.context('B-U1','B');share=SharingRepository(r)
  first=await publish(f,r,a,meta(False),docx_bytes());doc=UUID(first['document_id']);version=UUID(first['version_id'])
  assert (await share.readable(b,None,20))['items']==[]
  state=await share.control(a,doc,version)
  grant=await share.control(a,doc,version,'issue',f.tenant_ids['B'],expected=state['publication_revision'],request=uuid4())
  second=meta(False);second['expected_revision']=1
  await publish(f,r,a,second,docx_bytes(p('여신심사의 담당 부서는 변경팀이다.')),document=doc)
  assert [str(x['version_id']) for x in (await share.readable(b,None,20))['items']]==[first['version_id']]
  await share.control(a,action='revoke',grant=UUID(grant['grant_id']),expected=grant['revision'],request=uuid4())
  assert (await share.readable(b,None,20))['items']==[]
 f.run(check())
