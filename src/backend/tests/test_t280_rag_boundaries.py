"""Post-query token/quota failures preserve settled query cost and do not generate."""
from datetime import date
from uuid import UUID,uuid4
import pytest
from app.db import open_meter_pool
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage
from app.documents.embedding import MockEmbeddingProvider
from app.ai.rag_provider import RagMockProvider
from app.ai.repository import CallRepository,ExecutionError
from app.conversations.repository import ConversationRepository
from app.execution.rag import RagExecutor
from test_operations import ops_rows
from test_document_sharing import publish

@pytest.mark.parametrize('fault',['token','quota'])
def test_query_cost_survives_generation_gate_and_explicit_new_send(ops_rows,tmp_path,monkeypatch,fault):
 f=ops_rows
 class Query(MockEmbeddingProvider):
  def __init__(self):self.calls=0
  async def embed(self,*args):self.calls+=1;return await super().embed(*args)
 class Generate(RagMockProvider):
  def __init__(self):self.calls=0
  async def generate(self,*args):self.calls+=1;return await super().generate(*args)
 async def check():
  ctx=await f.context('A-U1','A');admin=await f.context('A-ADM','A');docs=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40);await publish(f,docs,admin)
  conversations=ConversationRepository(f.pool)
  async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
   repo=CallRepository(f.pool,meter,date(2026,10,1));query=Query();generate=Generate();engine=RagExecutor(repo,docs,query,generate)
   admitted=await conversations.admit(ctx,'rules_rag',None,uuid4(),'여신심사 담당 부서는?',date(2026,10,1),'mock',bytes(32),uuid4(),documents=docs);ticket=await repo.claim(ctx,UUID(admitted['run_id']),'mock')
   from app.execution import rag
   original_count=rag.general_token_count;original_packets=engine.search.packets
   if fault=='token':monkeypatch.setattr(rag,'general_token_count',lambda messages:6001)
   else:
    async def packets(*args):
     value=await original_packets(*args)
     with f.db.admin_connection() as c:c.execute("UPDATE ops.tenant_budgets SET local_cap_krw=accounted_krw WHERE tenant_id=%s",(ctx.tenant_id,))
     return value
    engine.search.packets=packets
   with pytest.raises(ExecutionError):await engine.execute(ticket)
   await repo.fail(ticket,'TOKEN_LIMIT_EXCEEDED' if fault=='token' else 'QUOTA_EXCEEDED')
   assert query.calls==1 and generate.calls==0
   with f.db.admin_connection() as c:
    first=c.execute('SELECT call_id,state,usage_snapshot FROM ops.call_attempts WHERE run_id=%s',(ticket.run.run_id,)).fetchone();assert first[1]=='settled' and first[2]
    assert c.execute("SELECT count(*) FROM portal.messages WHERE run_id=%s AND role='assistant'",(ticket.run.run_id,)).fetchone()[0]==0
   monkeypatch.setattr(rag,'general_token_count',original_count);engine.search.packets=original_packets
   with f.db.admin_connection() as c:c.execute('UPDATE ops.tenant_budgets SET local_cap_krw=allocated_cap_krw WHERE tenant_id=%s',(ctx.tenant_id,))
   # Only an explicit new accepted send can create a new query and generation.
   second=await conversations.admit(ctx,'rules_rag',None,uuid4(),'여신심사 담당 부서는?',date(2026,10,1),'mock',bytes(32),uuid4(),documents=docs);next_ticket=await repo.claim(ctx,UUID(second['run_id']),'mock');result=await engine.execute(next_ticket);assert await engine.finish(next_ticket,result)
   assert query.calls==2 and generate.calls==1 and second['run_id']!=admitted['run_id']
   with f.db.admin_connection() as c:
    assert c.execute('SELECT call_id,state,usage_snapshot FROM ops.call_attempts WHERE run_id=%s',(ticket.run.run_id,)).fetchone()==first
    assert c.execute("SELECT count(*) FROM ops.usage_events WHERE call_id=%s AND event_kind='settle'",(first[0],)).fetchone()[0]==1
 f.run(check())
