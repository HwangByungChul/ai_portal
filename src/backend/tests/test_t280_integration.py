"""Additional integrated ordering checks; all SQL mutation is owned-fixture only."""
from datetime import date
from uuid import UUID,uuid4
import pytest
from app.db import open_index_pool,open_meter_pool,tenant_transaction
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage
from app.documents.worker import DocumentWorker
from app.documents.embedding import EmbeddingGateway,MockEmbeddingProvider
from app.documents.search import SearchRepository
from app.ai.rag_provider import RagMockProvider
from app.ai.repository import CallRepository,ExecutionError
from app.conversations.repository import ConversationRepository
from app.execution.rag import RagExecutor
from app.errors import AppError
from test_operations import ops_rows
from test_document_ingest import metadata,RAW
from test_document_sharing import publish

@pytest.mark.parametrize('order',['delete_before_publish','publish_before_delete'])
def test_delete_publish_order_keeps_other_same_entity_document(ops_rows,tmp_path,order):
    f=ops_rows
    async def check():
        admin=await f.context('A-ADM','A');user=await f.context('A-U1','A');documents=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
        other=await publish(f,documents,admin,raw='여신심사의 기록 보관 담당 부서는 기록팀이다.'.encode())
        ids=await documents.register(admin,metadata(),RAW);deleted=False
        async def remove():
            nonlocal deleted
            await documents.delete(admin,UUID(ids['document_id']),1);deleted=True
        class DeleteAfterEmbed(MockEmbeddingProvider):
            async def embed(self,claim,texts,tokens):
                result=await super().embed(claim,texts,tokens)
                if order=='delete_before_publish':await remove()
                return result
        async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            worker=DocumentWorker(documents,EmbeddingGateway(index,meter,DeleteAfterEmbed(),date(2026,10,1)))
            if order=='delete_before_publish':
                with pytest.raises(Exception):await worker.run(admin,UUID(ids['job_id']))
            else:await worker.run(admin,UUID(ids['job_id']));await remove()
        assert deleted
        search=SearchRepository(documents);sources=await search.allowed(user,None,'mock')
        assert str(other['document_id']) in {x['document_id'] for x in sources} and str(ids['document_id']) not in {x['document_id'] for x in sources}
        with pytest.raises(AppError) as error:await search.allowed(user,[{'document_id':ids['document_id'],'version_id':ids['version_id']}],'mock')
        assert error.value.status==404
        with f.db.admin_connection() as conn:
            assert conn.execute('SELECT count(*) FROM security.document_publications WHERE document_id=%s AND active',(ids['document_id'],)).fetchone()[0]==0
            assert conn.execute('SELECT count(*) FROM rag.relations WHERE document_id=%s',(other['document_id'],)).fetchone()[0]==1
            assert conn.execute("SELECT count(*) FROM ops.call_attempts WHERE state='settled' AND operation='embed_document'").fetchone()[0]==2
    f.run(check())

@pytest.mark.parametrize('order',['revoke_before_admission','revoke_after_generation'])
def test_private_reader_membership_revocation_blocks_publish_without_erasing_cost(ops_rows,tmp_path,order):
    f=ops_rows
    async def check():
        admin=await f.context('A-ADM','A');reader=await f.context('A-U2','A');documents=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
        ids=await publish(f,documents,admin,metadata(visibility='private',owner_user_id=f.actor_ids['A-U1'],reader_ids=[f.actor_ids['A-U2']]))
        def revoke():
            # Reader-list edits are intentionally frozen in this MVP. Revoke the
            # reader's current organization membership in the owned fixture instead.
            f.mutate_access(reader,'membership')
        class RevokeAfterGenerate(RagMockProvider):
            async def generate(self,claim,messages,on_delta):
                result=await super().generate(claim,messages,on_delta);revoke();return result
        conversation=ConversationRepository(f.pool);refs=[{'document_id':UUID(ids['document_id']),'version_id':UUID(ids['version_id'])}]
        if order=='revoke_before_admission':
            revoke()
            with pytest.raises(AppError) as error:await conversation.admit(reader,'rules_rag',None,uuid4(),'여신심사 담당 부서는?',date(2026,10,1),'mock',bytes(32),uuid4(),refs=refs,documents=documents)
            assert error.value.status in (401,403)
        else:
            admitted=await conversation.admit(reader,'rules_rag',None,uuid4(),'여신심사 담당 부서는?',date(2026,10,1),'mock',bytes(32),uuid4(),refs=refs,documents=documents)
            async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
                repo=CallRepository(f.pool,meter,date(2026,10,1));ticket=await repo.claim(reader,UUID(admitted['run_id']),'mock');engine=RagExecutor(repo,documents,MockEmbeddingProvider(),RevokeAfterGenerate());result=await engine.execute(ticket)
                with pytest.raises(ExecutionError):await engine.finish(ticket,result)
                await repo.fail(ticket,'EXECUTION_BLOCKED')
        with f.db.admin_connection() as conn:assert conn.execute("SELECT count(*) FROM portal.messages WHERE role='assistant'").fetchone()[0]==0
        with f.db.admin_connection() as conn:
            assert conn.execute("SELECT count(*) FROM ops.call_attempts WHERE operation IN ('embed_query','generate_rag') AND state='settled'").fetchone()[0]==(0 if order=='revoke_before_admission' else 2)
            assert conn.execute('SELECT accounted_krw>0 FROM ops.project_budget WHERE mode=\'mock\'').fetchone()[0]
    f.run(check())

@pytest.mark.parametrize('order',['A_then_B','B_then_A'])
def test_document_scheduler_per_tenant_one_and_project_two(ops_rows,tmp_path,order):
    import asyncio
    from app.documents.manager import DocumentManager
    f=ops_rows
    async def check():
        admin_a=await f.context('A-ADM','A');admin_b=await f.context('B-ADM','B');documents=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
        jobs=[(admin_a,await documents.register(admin_a,metadata(),RAW)),(admin_a,await documents.register(admin_a,metadata(),RAW)),(admin_b,await documents.register(admin_b,metadata(),RAW))]
        class Block(MockEmbeddingProvider):
            def __init__(self):self.calls=0;self.two=asyncio.Event();self.release=asyncio.Event()
            async def embed(self,claim,texts,tokens):
                self.calls+=1
                if self.calls==2:self.two.set()
                await self.release.wait();return await super().embed(claim,texts,tokens)
        async with open_index_pool(f.db.runtime_dsn('ai_index'),size=2) as index,open_meter_pool(f.db.runtime_dsn('ai_meter'),size=2) as meter:
            provider=Block();manager=DocumentManager(DocumentWorker(documents,EmbeddingGateway(index,meter,provider,date(2026,10,1))),'mock')
            try:
                for ctx,ids in jobs if order=='A_then_B' else [jobs[2],jobs[0],jobs[1]]:manager.notify(ctx,UUID(ids['job_id']))
                await asyncio.wait_for(provider.two.wait(),5)
                with f.db.admin_connection() as conn:
                    states=conn.execute('SELECT tenant_id,state,count(*) FROM rag.jobs GROUP BY tenant_id,state').fetchall();assert sum(n for _,s,n in states if s=='running')==2
                    assert all(n<=1 for _,s,n in states if s=='running')
                    assert conn.execute('SELECT state FROM rag.jobs WHERE job_id=%s',(jobs[1][1]['job_id'],)).fetchone()[0]=='queued'
                    assert conn.execute("SELECT active_slot FROM ops.project_budget WHERE mode='mock'").fetchone()[0]==2
                    assert conn.execute("SELECT count(*) FROM ops.call_attempts").fetchone()[0]==2
                provider.release.set();await asyncio.wait_for(asyncio.gather(*list(manager.tasks.values())),10)
                with f.db.admin_connection() as conn:
                    assert conn.execute("SELECT count(*) FROM rag.jobs WHERE state='completed'").fetchone()[0]==3
                    assert conn.execute("SELECT count(*) FROM ops.call_attempts WHERE state='settled'").fetchone()[0]==3
                    assert conn.execute("SELECT active_slot FROM ops.project_budget WHERE mode='mock'").fetchone()[0]==0
                assert provider.calls==3
            finally:provider.release.set();await manager.close()
    f.run(check())

@pytest.mark.parametrize('order',['cancel_before_complete','complete_before_cancel'])
def test_terminal_cas_orders_preserve_late_usage_once(ops_rows,order):
    from app.ai.providers import MockProvider
    from test_ai_ledger import ticket,reserve_dispatch,budget
    from decimal import Decimal
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));t=await ticket(f,repo);claim=await reserve_dispatch(repo,t);provider=MockProvider();calls=0
            async def delta(text):pass
            outcome=await provider.generate(claim,t.messages,delta);calls+=1
            await repo.mark_unknown(t,claim,'unknown')
            conversations=ConversationRepository(f.pool)
            if order=='cancel_before_complete':
                view=await conversations.read(t.ctx,'run',t.run.run_id,None,20,bytes(32))
                requested=await conversations.cancel(t.ctx,t.run.run_id,view['revision'],uuid4());assert requested['state']=='cancel_requested'
                assert not await repo.finish(t,outcome.body)
                assert await repo.fail(t,'EXECUTION_INTERRUPTED')
            else:
                assert await repo.finish(t,outcome.body)
                view=await conversations.read(t.ctx,'run',t.run.run_id,None,20,bytes(32))
                preserved=await conversations.cancel(t.ctx,t.run.run_id,view['revision'],uuid4());assert preserved['state']=='completed'
                assert not await repo.fail(t,'EXECUTION_INTERRUPTED')
            for _ in range(2):await repo.settle(t,claim,outcome.receipt,'observed')
            with f.db.admin_connection() as conn:
                assert conn.execute('SELECT state FROM portal.runs WHERE run_id=%s',(t.run.run_id,)).fetchone()[0]==('cancelled' if order=='cancel_before_complete' else 'completed')
                assert conn.execute("SELECT count(*) FROM portal.messages WHERE run_id=%s AND role='assistant'",(t.run.run_id,)).fetchone()[0]==(0 if order=='cancel_before_complete' else 1)
                assert conn.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==1
                assert conn.execute("SELECT count(*) FROM ops.usage_events WHERE event_kind='settle'").fetchone()[0]==1
            assert calls==1 and budget(f)[:3]==(Decimal(0),Decimal('.11'),0)
            await provider.close()
    f.run(check())
