"""Actual independent PostgreSQL connections: shared-source revoke versus answer publication."""
from datetime import date
from uuid import UUID,uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from psycopg.types.json import Jsonb
import pytest
from app.db import open_meter_pool,tenant_transaction
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage
from app.documents.sharing import SharingRepository
from app.documents.embedding import MockEmbeddingProvider
from app.ai.rag_provider import RagMockProvider
from app.ai.repository import CallRepository
from app.conversations.repository import ConversationRepository
from app.execution.rag import RagExecutor
from test_operations import ops_rows
from test_document_sharing import publish

@pytest.mark.parametrize('iteration',[1,2,3])
def test_two_connection_grant_revoke_and_rag_publish(ops_rows,tmp_path,iteration):
 f=ops_rows
 async def prepare():
  admin=await f.context('A-ADM','A');reader=await f.context('B-U1','B');docs=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
  ids=await publish(f,docs,admin);grant=await SharingRepository(docs).control(admin,UUID(ids['document_id']),UUID(ids['version_id']),'issue',f.tenant_ids['B'],expected=1,request=uuid4())
  intake=await ConversationRepository(f.pool).admit(reader,'rules_rag',None,uuid4(),'여신심사 담당 부서는?',date(2026,10,1),'mock',bytes(32),uuid4(),documents=docs)
  async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
   repo=CallRepository(f.pool,meter,date(2026,10,1));ticket=await repo.claim(reader,UUID(intake['run_id']),'mock');engine=RagExecutor(repo,docs,MockEmbeddingProvider(),RagMockProvider());result=await engine.execute(ticket);await engine.stage(ticket,'finalizing');await engine.close()
  return admin,reader,grant,ticket,result
 admin,reader,grant,ticket,result=f.run(prepare());barrier=Barrier(2)
 def act(kind):
  ctx=admin if kind=='revoke' else reader
  with f.role_connection('ai_web') as c:
   c.autocommit=False;pid=c.execute('SELECT pg_backend_pid()').fetchone()[0]
   for key,value in [('app.user_id',ctx.user_id),('app.tenant_id',ctx.tenant_id),('app.session_id',ctx.session_id)]:c.execute('SELECT set_config(%s,%s,true)',(key,str(value)))
   barrier.wait(timeout=5)
   try:
    if kind=='revoke':v=c.execute('SELECT security.document_share_control(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(admin.session_id,admin.tenant_id,None,None,'revoke',None,UUID(grant['grant_id']),1,uuid4())).fetchone()[0]
    else:v=c.execute('SELECT security.rag_finish(%s,%s,%s,%s,%s,%s,%s,%s)',(*CallRepository(None,None,None).worker_args(ticket),result.body,result.answer_kind,Jsonb(list(result.evidence)))).fetchone()[0]
    c.commit();return kind,pid,True,v
   except Exception as error:
    c.rollback();assert kind=='finish' and getattr(error,'sqlstate',None) in ('A0404','B0405','B0401');return kind,pid,False,None
 with ThreadPoolExecutor(max_workers=2) as e:out=list(e.map(act,['revoke','finish']))
 assert out[0][1]!=out[1][1] and out[0][2]
 async def reconcile():
  async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:await CallRepository(f.pool,meter,date(2026,10,1)).fail(ticket,'EXECUTION_BLOCKED')
  async with tenant_transaction(f.pool,reader) as c:
   assert await (await c.execute("SELECT body FROM portal.messages WHERE run_id=%s AND role='assistant'",(ticket.run.run_id,))).fetchone() is None
 f.run(reconcile())
 with f.db.admin_connection() as c:
  assert not c.execute('SELECT active FROM security.share_grants WHERE grant_id=%s',(grant['grant_id'],)).fetchone()[0]
  assert c.execute('SELECT state FROM portal.runs WHERE run_id=%s',(ticket.run.run_id,)).fetchone()[0] in ('completed','failed')
  assert c.execute("SELECT count(*) FROM ops.call_attempts WHERE run_id=%s AND state='settled'",(ticket.run.run_id,)).fetchone()[0]==2
  assert c.execute('SELECT count(*) FROM ops.call_attempts WHERE slot_held').fetchone()[0]==0
