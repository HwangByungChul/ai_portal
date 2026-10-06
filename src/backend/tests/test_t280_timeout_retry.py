"""Timed-out remote work retains its reservation across stop/resume/replay."""
import asyncio
from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from app.db import open_meter_pool
from app.ai.repository import CallRepository
from app.ai.gateway import AiGateway
from app.ai.providers import MockProvider
from app.conversations.repository import ConversationRepository
from app.errors import AppError
from test_operations import ops_rows
from test_ai_ledger import ticket,budget

@pytest.mark.parametrize('control',['agent','tenant','project','cap'])
def test_timeout_then_stop_resume_never_replays_remote_call(ops_rows,control):
 f=ops_rows
 class Timeout(MockProvider):
  def __init__(self):self.calls=0
  async def generate(self,*args):self.calls+=1;raise asyncio.TimeoutError()
 async def check():
  async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
   repo=CallRepository(f.pool,meter,date(2026,10,1));t=await ticket(f,repo);provider=Timeout();gateway=AiGateway(repo,provider)
   async def delta(text):pass
   result=await gateway.execute(t,delta);assert result.body is None and provider.calls==1
   await repo.fail(t,result.safe_error_code or 'STREAM_INTERRUPTED')
   before=budget(f)[:3];assert before==(Decimal('3.64'),Decimal(0),1)
   with f.db.admin_connection() as c:
    if control=='agent':c.execute("UPDATE portal.agent_configs SET enabled=false WHERE tenant_id=%s AND agent_key='general'",(t.ctx.tenant_id,))
    elif control=='tenant':c.execute("UPDATE ops.tenant_budgets SET stopped=true WHERE tenant_id=%s",(t.ctx.tenant_id,))
    elif control=='project':c.execute("UPDATE ops.project_budget SET stopped=true WHERE mode='mock'")
    else:c.execute("UPDATE ops.project_budget SET operational_cap_krw=0 WHERE mode='mock'")
   # Same accepted send is reconciled, never resubmitted to the provider.
   with f.db.admin_connection() as c:
    send=c.execute('SELECT client_send_id FROM portal.runs WHERE run_id=%s',(t.run.run_id,)).fetchone()[0]
   conversations=ConversationRepository(f.pool)
   replay=await conversations.admit(t.ctx,'general',None,send,t.messages[-1]['content'],date(2026,10,1),'mock',bytes(32),uuid4())
   assert str(replay['run_id'])==str(t.run.run_id)
   with pytest.raises(AppError):await conversations.admit(t.ctx,'general',None,uuid4(),'새 합성 질문',date(2026,10,1),'mock',bytes(32),uuid4())
   with f.db.admin_connection() as c:
    if control=='agent':c.execute("UPDATE portal.agent_configs SET enabled=true WHERE tenant_id=%s AND agent_key='general'",(t.ctx.tenant_id,))
    elif control=='tenant':c.execute("UPDATE ops.tenant_budgets SET stopped=false WHERE tenant_id=%s",(t.ctx.tenant_id,))
    elif control=='project':c.execute("UPDATE ops.project_budget SET stopped=false WHERE mode='mock'")
    else:c.execute("UPDATE ops.project_budget SET operational_cap_krw=25000 WHERE mode='mock'")
   # Resume cannot clear an unknown remote end or its occupied slot.
   try:
    fresh=await conversations.admit(t.ctx,'general',None,uuid4(),'재개 후 합성 질문',date(2026,10,1),'mock',bytes(32),uuid4())
   except AppError:pass
   else:
    from uuid import UUID
    fresh_ticket=await repo.claim(t.ctx,UUID(fresh['run_id']),'mock')
    outcome=await gateway.execute(fresh_ticket,delta);assert outcome.body is None and outcome.safe_error_code
    await repo.fail(fresh_ticket,outcome.safe_error_code)
   assert budget(f)[:3]==before
   with f.db.admin_connection() as c:
    assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==1
    assert c.execute("SELECT state,slot_held FROM ops.call_attempts").fetchone()==('usage_unknown',True)
    assert c.execute("SELECT count(*) FROM portal.messages WHERE role='assistant'").fetchone()[0]==0
   assert provider.calls==1
 f.run(check())
