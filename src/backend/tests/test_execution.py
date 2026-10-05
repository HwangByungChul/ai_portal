import asyncio
from datetime import date
from dataclasses import replace
from decimal import Decimal
import json
from uuid import UUID,uuid4
import pytest
from app.ai.gateway import AiGateway
from app.ai.repository import CallRepository,ExecutionError,DispatchUncertain,digest
from app.ai.providers import MockProvider
from app.ai.types import ProviderOutcome,UsageReceipt
from app.execution.manager import ExecutionManager
from app.execution.stream import StreamHub
from app.db import open_web_pool,open_meter_pool
from app.conversations.repository import ConversationRepository
from test_operations import ops_rows,headers
from test_ai_ledger import ticket,reserve_dispatch,budget

class CountingProvider(MockProvider):
    def __init__(self):self.calls=0;self.entered=asyncio.Event();self.release=asyncio.Event();self.closed=False;self.block=False
    async def generate(self,claim,messages,on_delta):
        self.calls+=1;self.entered.set()
        if self.block:
            await on_delta('저장 전 비공개 합성 초안');await self.release.wait()
        return await super().generate(claim,messages,on_delta)
    async def close(self):self.closed=True

async def submit(f,repo):
    ctx=await f.context('A-U1','A')
    data=await ConversationRepository(repo.web_pool).admit(ctx,'general',None,uuid4(),'합성 실행 질문',date(2026,10,1),'mock',bytes(32),uuid4())
    return ctx,UUID(data['run_id'])

async def wait_done(manager):
    tasks=list(manager.tasks.values());await asyncio.wait_for(asyncio.gather(*tasks),10)
    await asyncio.sleep(0)

@pytest.mark.parametrize('case',['complete','save_retry','save_commit_loss','save_fail','cancel','revoke','disable','missing_usage','unknown','meter_fail','truncated'])
def test_execution_manager_terminal_and_failure_paths(ops_rows,case):
    f=ops_rows
    async def check():
        async with open_web_pool(f.db.runtime_dsn()) as web,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(web,meter,date(2026,10,1));provider=CountingProvider();hub=StreamHub();manager=ExecutionManager(repo,provider,'mock',hub)
            await manager.start();ctx,run=await submit(f,repo)
            try:
                original_finish=repo.finish;finish_calls=0
                async def finish(t,body):
                    nonlocal finish_calls
                    finish_calls+=1
                    if case=='save_fail' or (case=='save_retry' and finish_calls==1):raise ExecutionError('LEDGER_UNAVAILABLE')
                    saved=await original_finish(t,body)
                    if case=='save_commit_loss' and finish_calls==1:raise ExecutionError('LEDGER_UNAVAILABLE')
                    return saved
                repo.finish=finish
                if case in ('cancel','revoke','disable'):provider.block=True
                original_generate=provider.generate
                if case in ('missing_usage','unknown','truncated'):
                    async def special(claim,messages,on_delta):
                        provider.calls+=1
                        if case=='missing_usage':return ProviderOutcome('합성 사용량 미확인 답변',None,'observed',None)
                        return ProviderOutcome(None,None,'unknown','STREAM_INTERRUPTED') if case=='unknown' else ProviderOutcome(None,UsageReceipt(120,40,160,'gpt-4o-mini','default',None),'observed','OUTPUT_TRUNCATED')
                    provider.generate=special
                if case=='meter_fail':
                    async def bad_settle(*args,**kwargs):raise ExecutionError('LEDGER_UNAVAILABLE')
                    repo.settle=bad_settle
                manager.notify(ctx,run);manager.notify(ctx,run)
                if provider.block:
                    await asyncio.wait_for(provider.entered.wait(),5)
                    for _ in range(100):
                        if hub.drafts.get((ctx.tenant_id,run),{}).get('text'):break
                        await asyncio.sleep(.01)
                    assert hub.drafts[(ctx.tenant_id,run)]['text']
                    if case=='cancel':
                        data=await ConversationRepository(web).read(ctx,'run',run,None,20,bytes(32))
                        await ConversationRepository(web).cancel(ctx,run,data['revision'],uuid4());manager.cancel(ctx,run)
                    elif case=='revoke':f.mutate_access(ctx,'revoked');provider.release.set()
                    else:
                        with f.db.admin_connection() as conn:conn.execute("UPDATE portal.agent_configs SET enabled=false WHERE tenant_id=%s AND agent_key='general'",(ctx.tenant_id,))
                        provider.release.set()
                await wait_done(manager)
                with f.db.admin_connection() as conn:
                    state=conn.execute('SELECT state,safe_error_code FROM portal.runs WHERE run_id=%s',(run,)).fetchone()
                    assistants=conn.execute("SELECT count(*) FROM portal.messages WHERE run_id=%s AND role='assistant'",(run,)).fetchone()[0]
                assert provider.calls==1 and not hub.drafts
                if case in ('complete','save_retry','save_commit_loss'):assert state==('completed',None) and assistants==1 and budget(f)[1]==Decimal('.11')
                elif case=='missing_usage':assert state==('completed',None) and assistants==1 and budget(f)[:3]==(Decimal('3.64'),Decimal(0),0)
                elif case=='cancel':assert state[0]=='cancelled' and assistants==0 and budget(f)[0]==Decimal('3.64') and budget(f)[2]==1
                elif case in ('revoke','disable'):assert state[0]=='failed' and assistants==0 and budget(f)[:3]==(Decimal('3.64'),Decimal(0),1)
                else:
                    assert state[0]=='failed' and assistants==0
                    if case=='save_fail':assert state[1]=='RESULT_SAVE_FAILED' and finish_calls==2 and budget(f)[1]==Decimal('.11')
                    if case=='meter_fail':assert manager.gateway.stop_latch and state[1]=='LEDGER_UNAVAILABLE'
                assert finish_calls== (2 if case in ('save_retry','save_commit_loss','save_fail') else 1 if case in ('complete','missing_usage') else 0)
                await manager.close();assert provider.closed and not manager.tasks and not hub.subscriptions
            finally:await manager.close()
    f.run(check())

@pytest.mark.parametrize('phase',['reserve','dispatch'])
def test_unconfirmed_commit_never_calls_provider(ops_rows,phase):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));t=await ticket(f,repo);provider=CountingProvider();gateway=AiGateway(repo,provider)
            if phase=='reserve':
                original=repo.reserve
                async def uncertain(*args):
                    await original(*args);raise ExecutionError('LEDGER_UNAVAILABLE')
                repo.reserve=uncertain
            else:
                original=repo.dispatch
                async def uncertain(*args):
                    claim=await original(*args);raise DispatchUncertain(claim)
                repo.dispatch=uncertain
            outcome=await gateway.execute(t,lambda x:None)
            assert provider.calls==0 and outcome.body is None and outcome.safe_error_code=='LEDGER_UNAVAILABLE'
            with f.db.admin_connection() as conn:
                state=conn.execute('SELECT state,dispatched_at IS NULL FROM ops.call_attempts').fetchone()
                assert state==('reserved',True) if phase=='reserve' else state==('usage_unknown',False)
            assert budget(f)[:3]==(Decimal('3.64'),Decimal(0),1)
    f.run(check())

def test_stream_rechecks_before_each_body_and_bounds_subscriptions():
    from types import SimpleNamespace
    hub=StreamHub();ctx=SimpleNamespace(user_id=uuid4(),tenant_id=uuid4());run=uuid4()
    view={'tenant_id':str(ctx.tenant_id),'run_id':str(run),'execution_epoch':1,'revision':2,'state':'running','is_terminal':False,'result':None}
    class Repo:
        def __init__(self):self.allowed=True;self.calls=0
        async def stream_view(self,*args):
            self.calls+=1
            if not self.allowed:raise ExecutionError('EXECUTION_BLOCKED')
            return dict(view)
    async def check():
        repo=Repo();key=hub.acquire(ctx,run)
        with pytest.raises(Exception,match='STREAM_LIMIT_REACHED'):hub.acquire(ctx,run)
        t=SimpleNamespace(tenant_id=ctx.tenant_id,run_id=run,epoch=1);hub.begin(t);hub.append(t,'비공개 합성 초안')
        events=hub.events(ctx,run,repo,'mock',key);assert 'event: snapshot' in await anext(events)
        repo.allowed=False;reply=await anext(events)
        assert 'delivery_error' in reply and '비공개 합성 초안' not in reply and repo.calls==2
        with pytest.raises(StopAsyncIteration):await anext(events)
        assert not hub.subscriptions
        hub.acquire(ctx,run);hub.acquire(ctx,uuid4())
        with pytest.raises(Exception,match='STREAM_LIMIT_REACHED'):hub.acquire(ctx,uuid4())
        hub.clear(t);assert not hub.drafts;hub.close();assert not hub.subscriptions
    asyncio.run(check())

def test_stream_snapshot_reconnect_and_post_commit_terminal_do_not_start_provider(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));t=await ticket(f,repo);provider=CountingProvider();gateway=AiGateway(repo,provider)
            async def delta(text):pass
            outcome=await gateway.execute(t,delta);assert await repo.finish(t,outcome.body)
            hub=StreamHub()
            for _ in range(2):
                key=hub.acquire(t.ctx,t.run.run_id);events=[]
                async for event in hub.events(t.ctx,t.run.run_id,repo,'mock',key):events.append(event)
                assert len(events)==2 and 'snapshot' in events[0] and 'terminal' in events[1] and outcome.body in events[1]
            assert provider.calls==1 and not hub.subscriptions
    f.run(check())

def test_single_execution_leader_shutdown_cleans_claims_and_pool(ops_rows):
    f=ops_rows
    async def check():
        async with open_web_pool(f.db.runtime_dsn()) as web,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(web,meter,date(2026,10,1));one=ExecutionManager(repo,CountingProvider(),'mock',StreamHub());two=ExecutionManager(repo,CountingProvider(),'mock',StreamHub())
            await one.start()
            with pytest.raises(ExecutionError):await two.start()
            await two.close();await one.close()
            three=ExecutionManager(repo,CountingProvider(),'mock',StreamHub());await three.start();await three.close()
    f.run(check())
