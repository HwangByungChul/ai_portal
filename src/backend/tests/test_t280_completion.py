from datetime import date
from uuid import UUID,uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from decimal import Decimal
import pytest
from app.db import open_meter_pool
from app.ai.repository import CallRepository,digest
from app.ai.providers import MockProvider
from app.conversations.repository import ConversationRepository
from test_operations import ops_rows
from test_ai_ledger import ticket,reserve_dispatch,budget

@pytest.mark.parametrize('iteration',[1,2,3])
def test_real_two_connection_cancel_complete_cas(ops_rows,iteration):
    f=ops_rows
    async def admit():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));t=await ticket(f,repo);claim=await reserve_dispatch(repo,t);provider=MockProvider()
            async def delta(text):pass
            outcome=await provider.generate(claim,t.messages,delta);await provider.close();await repo.mark_unknown(t,claim)
            view=await ConversationRepository(f.pool).read(t.ctx,'run',t.run.run_id,None,20,bytes(32));return t,claim,outcome,view['revision']
    t,claim,outcome,revision=f.run(admit());barrier=Barrier(2)
    def act(kind):
        with f.role_connection('ai_web') as c:
            pid=c.execute('SELECT pg_backend_pid()').fetchone()[0]
            c.autocommit=False
            for key,value in (('app.user_id',t.ctx.user_id),('app.tenant_id',t.ctx.tenant_id),('app.session_id',t.ctx.session_id)):
                c.execute('SELECT set_config(%s,%s,true)',(key,str(value)))
            barrier.wait(timeout=5)
            if kind=='cancel':result=c.execute('SELECT security.run_cancel(%s,%s,%s,%s,%s)',(t.ctx.session_id,t.ctx.tenant_id,t.run.run_id,revision,uuid4())).fetchone()[0]
            else:result=c.execute('SELECT security.execution_finish(%s,%s,%s,%s,%s,%s)',(*CallRepository(None,None,None).worker_args(t),outcome.body)).fetchone()[0]
            c.commit()
            return kind,pid,result
    with ThreadPoolExecutor(max_workers=2) as ex:results=list(ex.map(act,['cancel','finish']))
    assert results[0][1]!=results[1][1]
    async def reconcile():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));await repo.fail(t,'EXECUTION_INTERRUPTED')
            for _ in range(2):await repo.settle(t,claim,outcome.receipt,'observed')
    f.run(reconcile())
    with f.db.admin_connection() as c:
        state=c.execute('SELECT state FROM portal.runs WHERE run_id=%s',(t.run.run_id,)).fetchone()[0];assert state in ('cancelled','completed')
        assert c.execute("SELECT count(*) FROM portal.messages WHERE run_id=%s AND role='assistant'",(t.run.run_id,)).fetchone()[0]==int(state=='completed')
        assert c.execute('SELECT count(*) FROM ops.call_attempts WHERE run_id=%s',(t.run.run_id,)).fetchone()[0]==1
        assert c.execute("SELECT count(*) FROM ops.usage_events WHERE call_id=%s AND event_kind='settle'",(claim.call_id,)).fetchone()[0]==1
        assert c.execute('SELECT state,slot_held FROM ops.call_attempts WHERE call_id=%s',(claim.call_id,)).fetchone()==('settled',False)
    assert budget(f)[:3]==(Decimal(0),Decimal('.11'),0)
