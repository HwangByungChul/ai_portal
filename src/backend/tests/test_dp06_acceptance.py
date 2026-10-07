import hashlib
from dataclasses import replace
from uuid import UUID,uuid4
from datetime import date
import pytest
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage,StoredSource,SourceStorageError
from app.documents.worker import DocumentWorker
from app.documents.embedding import EmbeddingGateway
from app.db import open_index_pool,open_meter_pool
from app.errors import AppError
from test_document_ingest import ingest,metadata,RAW
from test_document_jobs import CountingEmbedding
from test_operations import ops_rows
from pdf_support import pdf_bytes

@pytest.mark.parametrize('personal',[False,True])
def test_pdf_original_canonical_hash_and_replay_without_parser(ingest,monkeypatch,personal):
 f,r=ingest;ctx=f.run(f.context('A-U1' if personal else 'A-ADM','A'))
 m=metadata(media_type='application/pdf')
 if personal:m={k:m[k] for k in ('client_upload_id','title','media_type')}
 raw=pdf_bytes([RAW.decode(),'합성 두 번째 페이지.']);ids=f.run(r.register(ctx,m,raw,personal=personal))
 with f.db.admin_connection() as c:
  row=c.execute('SELECT source_object_key,source_sha256,byte_length,character_length,title,media_type,source_mapping FROM rag.document_versions').fetchone()
 stored=StoredSource(row[0],bytes(row[1]),*row[2:])
 canonical=r.storage.read(stored);assert canonical==RAW+b'\n\n'+'합성 두 번째 페이지.'.encode()
 assert r.storage.read_original(stored)==raw
 assert stored.source_mapping['origin']['source_sha256']==hashlib.sha256(raw).hexdigest()
 assert stored.sha256==hashlib.sha256(canonical).digest()
 import app.documents.repository as module
 monkeypatch.setattr(module,'extract_pdf',lambda _:pytest.fail('replayed PDF must not parse'))
 again=f.run(r.register(ctx,m,raw,personal=personal));assert again['replayed'] and again['job_id']==ids['job_id']

@pytest.mark.parametrize('personal',[False,True])
def test_denied_authorization_precedes_parser(ingest,monkeypatch,personal):
 f,r=ingest;ctx=f.run(f.context('A-U1' if personal else 'A-ADM','A'));f.mutate_access(ctx,'membership')
 import app.documents.repository as module
 monkeypatch.setattr(module,'extract_pdf',lambda _:pytest.fail('denied principal must not parse'))
 m=metadata(media_type='application/pdf')
 if personal:m={k:m[k] for k in ('client_upload_id','title','media_type')}
 with pytest.raises(AppError):f.run(r.register(ctx,m,pdf_bytes(['safe']),personal=personal))
 assert not list(r.storage.root.rglob('source'))

@pytest.mark.parametrize('media,body',[('text/plain',b'Contact sample@example.invalid'),('text/markdown',b'---\nemail: sample@example.invalid\n---\nSafe body'),('application/pdf',pdf_bytes(['Contact sample@example.invalid']))])
def test_policy_blocks_before_storage_job_or_provider(ingest,media,body):
 f,r=ingest;ctx=f.run(f.context('A-ADM','A'))
 with pytest.raises(AppError) as e:f.run(r.register(ctx,metadata(media_type=media),body))
 assert e.value.code=='DOCUMENT_POLICY_BLOCKED' and not list(r.storage.root.rglob('source'))
 with f.db.admin_connection() as c:
  assert c.execute('SELECT count(*) FROM rag.jobs').fetchone()==(0,)
  assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()==(0,)

def test_rejected_pdf_attempts_consume_admission_before_parser(ingest):
 f,r=ingest;ctx=f.run(f.context('A-ADM','A'))
 for _ in range(10):
  with pytest.raises(AppError) as e:f.run(r.register(ctx,metadata(media_type='application/pdf'),b'%PDF-1.7 broken'))
  assert e.value.code=='PDF_INVALID'
 with pytest.raises(AppError) as e:f.run(r.register(ctx,metadata(media_type='application/pdf'),pdf_bytes(['safe'])))
 assert e.value.code=='RATE_LIMITED' and not list(r.storage.root.rglob('source'))

def test_original_corruption_and_pair_cleanup(ingest):
 f,r=ingest;ctx=f.run(f.context('A-ADM','A'));ids=f.run(r.register(ctx,metadata(media_type='application/pdf'),pdf_bytes([RAW.decode()])))
 with f.db.admin_connection() as c:row=c.execute('SELECT source_object_key,source_sha256,byte_length,character_length,title,media_type,source_mapping FROM rag.document_versions').fetchone()
 stored=StoredSource(row[0],bytes(row[1]),*row[2:]);original=(r.storage.root/stored.object_key).with_name('original');original.write_bytes(b'corrupt')
 with pytest.raises(SourceStorageError):r.storage.read(stored)
 assert r.storage.remove(stored.object_key)==1 and not original.exists()
 assert r.storage.remove(stored.object_key)==0

def test_original_only_orphan_cleanup(ingest):
 f,r=ingest;ctx=f.run(f.context('A-ADM','A'));key=f'tenants/{ctx.tenant_id}/documents/{uuid4()}/{uuid4()}/source';raw=pdf_bytes(['safe'])
 r.storage.write_original(key,raw,hashlib.sha256(raw).digest())
 assert key in r.storage.source_keys(ctx.tenant_id)
 assert r.storage.remove(key)==1

def test_worker_policy_blocks_legacy_source_before_embedding(ops_rows,tmp_path,monkeypatch):
 f=ops_rows;r=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
 async def check():
  import app.documents.repository as module
  with monkeypatch.context() as scope:
   scope.setattr(module,'require_document_policy',lambda _:None)
   ctx=await f.context('A-ADM','A');ids=await r.register(ctx,metadata(),b'Contact sample@example.invalid')
  provider=CountingEmbedding()
  async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
   with pytest.raises(AppError) as e:await DocumentWorker(r,EmbeddingGateway(index,meter,provider,date(2026,10,1))).run(ctx,UUID(ids['job_id']))
  assert e.value.code=='DOCUMENT_POLICY_BLOCKED' and provider.calls==0
  assert (await r.job(ctx,UUID(ids['job_id'])))['state']=='failed'
 f.run(check())
