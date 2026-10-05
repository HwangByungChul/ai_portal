import asyncio
from datetime import date
from uuid import UUID
import pytest
from app.db import make_index_pool,open_meter_pool
from app.documents.worker import DocumentWorker
from app.documents.embedding import EmbeddingGateway,MockEmbeddingProvider
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage
from app.documents.policy import resolve_readable_version
from test_document_ingest import metadata,RAW
from test_operations import ops_rows

class CountingEmbedding(MockEmbeddingProvider):
    def __init__(self,case='complete'):self.calls=0;self.case=case
    async def embed(self,claim,texts,tokens):
        self.calls+=1
        if self.case=='unknown':raise TimeoutError()
        values,receipt=await super().embed(claim,texts,tokens)
        if self.case=='bad_vector':values[0]=[0]*1536
        return values,receipt

@pytest.mark.parametrize('case',['complete','unknown','bad_vector'])
def test_scoped_worker_persists_or_holds_without_redispatch(ops_rows,tmp_path,case):
    f=ops_rows
    async def check():
        ctx=await f.context('A-ADM','A');repo=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
        result=await repo.register(ctx,metadata(),RAW);job=UUID(result['job_id']);index=UUID(result['index_id'])
        pool=make_index_pool(f.db.runtime_dsn('ai_index'),1);await pool.open();await pool.wait(timeout=5)
        provider=CountingEmbedding(case)
        try:
            async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
                worker=DocumentWorker(repo,EmbeddingGateway(pool,meter,provider,date(2026,10,1)))
                if case=='complete':await worker.run(ctx,job)
                else:
                    with pytest.raises(Exception):await worker.run(ctx,job)
                view=await repo.job(ctx,job)
                assert view['state']==('completed' if case=='complete' else 'needs_review')
                await worker.run(ctx,job);assert provider.calls==1
                if case=='complete':assert (await resolve_readable_version(f.pool,ctx,UUID(result['document_id']))).index_id==index
                with f.db.admin_connection() as c:
                    assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==1
                    assert c.execute('SELECT count(*) FROM rag.chunks WHERE index_id=%s',(index,)).fetchone()[0]==(1 if case=='complete' else 0)
                    assert c.execute('SELECT count(*) FROM security.document_publications WHERE active').fetchone()[0]==(1 if case=='complete' else 0)
                    if case=='complete':
                        assert c.execute("SELECT state,slot_held,operation,run_id FROM ops.call_attempts").fetchone()==('settled',False,'embed_document',None)
                        assert c.execute('SELECT count(*) FROM rag.relations').fetchone()[0]==1
                    else:assert c.execute('SELECT state FROM ops.call_attempts').fetchone()[0]=='usage_unknown'
        finally:await pool.close()
    f.run(check())

def test_claim_is_exclusive_and_epoch_fences(ops_rows,tmp_path):
    f=ops_rows;ctx=f.run(f.context('A-ADM','A'));repo=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
    result=f.run(repo.register(ctx,metadata(),RAW));job=UUID(result['job_id']);claim=bytes(range(32))
    first=f.run(repo.job(ctx,job,'claim',claim=claim));assert first['epoch']==2
    assert f.run(repo.job(ctx,job,'claim',claim=b'x'*32)) is None
    from app.errors import AppError
    with pytest.raises(AppError):f.run(repo.job(ctx,job,'heartbeat',1,claim))
    f.mutate_access(ctx,'membership')
    with pytest.raises(AppError):f.run(repo.job(ctx,job,'heartbeat',2,claim))

def test_known_checkpoint_survives_expired_worker_without_provider_repeat(ops_rows,tmp_path):
    import hashlib
    from app.documents.plan import build_document_plan
    from common_core.ai_pipeline.document.schemas import DocumentMetadata
    f=ops_rows
    async def check():
        ctx=await f.context('A-ADM','A');repo=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40);ids=await repo.register(ctx,metadata(),RAW);job=UUID(ids['job_id'])
        claim=b'a'*32;owned=await repo.job(ctx,job,'claim',claim=claim);ticket={'tenant_id':ctx.tenant_id,'job_id':job,'epoch':owned['epoch'],'claim':claim}
        plan=build_document_plan(RAW,'합성 시험','text/plain',DocumentMetadata(ctx.tenant_id,UUID(ids['document_id']),UUID(ids['version_id']),UUID(ids['index_id']),hashlib.sha256(RAW).digest(),'mock'))
        await repo.job(ctx,job,'plan',ticket['epoch'],claim,{'batches':len(plan.batches),'fingerprint':plan.source_fingerprint,'coverage':{'status':plan.graph.coverage}})
        pool=make_index_pool(f.db.runtime_dsn('ai_index'),1);await pool.open();await pool.wait(timeout=5)
        try:
            async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
                provider=CountingEmbedding();gateway=EmbeddingGateway(pool,meter,provider,date(2026,10,1));worker=DocumentWorker(repo,gateway);batch=plan.batches[0]
                call,vectors=await gateway.batch(ticket,batch,[plan.chunks[x].text for x in batch.chunk_ordinals]);await worker._save_batch(ticket,plan,batch,call,vectors)
                # Persisted checkpoint represents the interruption boundary; no test expectation is loaded into runtime.
                with f.db.admin_connection() as c:
                    c.execute("UPDATE rag.jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE job_id=%s",(job,))
                    c.execute("UPDATE security.job_authorizations SET expires_at=clock_timestamp()-interval '1 second' WHERE job_id=%s",(job,))
                await worker.run(ctx,job);assert provider.calls==1 and (await repo.job(ctx,job))['state']=='completed'
                with f.db.admin_connection() as c:assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==1
        finally:await pool.close()
    f.run(check())

def test_publish_revocation_rolls_back_and_keeps_payload_unpublished(ops_rows,tmp_path):
    f=ops_rows
    class Revoke(CountingEmbedding):
        async def embed(self,claim,texts,tokens):
            outcome=await super().embed(claim,texts,tokens)
            with f.db.admin_connection() as c:c.execute("UPDATE portal.agent_configs SET enabled=false WHERE tenant_id=%s AND agent_key='rules_rag'",(f.tenant_ids['A'],))
            return outcome
    async def check():
        ctx=await f.context('A-ADM','A');repo=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40);ids=await repo.register(ctx,metadata(),RAW)
        pool=make_index_pool(f.db.runtime_dsn('ai_index'),1);await pool.open();await pool.wait(timeout=5)
        try:
            async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
                provider=Revoke();worker=DocumentWorker(repo,EmbeddingGateway(pool,meter,provider,date(2026,10,1)))
                with pytest.raises(Exception):await worker.run(ctx,UUID(ids['job_id']))
                assert provider.calls==1
                with f.db.admin_connection() as c:
                    assert c.execute('SELECT count(*) FROM security.document_publications WHERE active').fetchone()[0]==0
                    assert c.execute('SELECT state FROM ops.call_attempts').fetchone()[0]=='settled'
        finally:await pool.close()
    f.run(check())

def test_real_job_cannot_be_claimed_by_mock_server(ops_rows,tmp_path):
    from app.errors import AppError
    f=ops_rows;ctx=f.run(f.context('A-ADM','A'));storage=SourceStorage(tmp_path/'sources')
    real=DocumentRepository(f.pool,storage,'x'*40,'real');mock=DocumentRepository(f.pool,storage,'x'*40,'mock')
    ids=f.run(real.register(ctx,metadata(),RAW))
    with pytest.raises(AppError):f.run(mock.job(ctx,UUID(ids['job_id']),'claim',claim=b'x'*32))
    assert f.run(mock.job(ctx,UUID(ids['job_id'])))['state']=='queued'
    with pytest.raises(ValueError,match='INDEX_MODE_MISMATCH'):DocumentWorker(real,EmbeddingGateway(None,None,MockEmbeddingProvider(),date(2026,10,1)))

@pytest.mark.parametrize('mutation',['revoked','agent'])
def test_raw_index_read_rechecks_origin_and_agent(ops_rows,tmp_path,mutation):
    f=ops_rows;ctx=f.run(f.context('A-ADM','A'));repo=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
    ids=f.run(repo.register(ctx,metadata(visibility='private',owner_user_id=f.actor_ids['A-U1']),RAW));claim=b'z'*32;job=UUID(ids['job_id']);f.run(repo.job(ctx,job,'claim',claim=claim))
    with f.role_connection('ai_index') as c:
        with c.transaction():
            for k,v in [('app.job_id',job),('app.job_epoch',2),('app.job_tenant_id',ctx.tenant_id),('app.job_claim',claim.hex())]:c.execute('SELECT set_config(%s,%s,true)',(k,str(v)))
            assert len(c.execute('SELECT version_id FROM rag.document_versions').fetchall())==1
            if mutation=='revoked':f.mutate_access(ctx,'revoked')
            else:
                with f.db.admin_connection() as admin:admin.execute("UPDATE portal.agent_configs SET enabled=false WHERE tenant_id=%s AND agent_key='rules_rag'",(ctx.tenant_id,))
            assert c.execute('SELECT version_id FROM rag.document_versions').fetchall()==[]
