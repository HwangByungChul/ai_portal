import asyncio
import hashlib
from uuid import UUID,uuid4
from decimal import Decimal
from dataclasses import replace
import pytest
import psycopg
from app.ai.repository import CallRepository,ExecutionError,digest
from app.ai.types import UsageReceipt
from app.ai.gateway import AiGateway
from app.ai.providers import MockProvider
from app.db import open_meter_pool,open_web_pool
from app.conversations.repository import ConversationRepository
from test_operations import ops_rows

async def ticket(f,repo,actor='A-U1',tenant='A'):
    ctx=await f.context(actor,tenant)
    data=await ConversationRepository(repo.web_pool).admit(ctx,'general',None,uuid4(),'합성 실행 질문',repo.period,'mock',hashlib.sha256(uuid4().bytes).digest(),uuid4())
    return await repo.claim(ctx,UUID(data['run_id']),'mock')

async def reserve_dispatch(repo,t):
    data=await repo.reserve(t,hashlib.sha256(b'synthetic').digest())
    c=await repo.dispatch(t,UUID(data['call_id']));assert c is not None;return c

def budget(f,tenant='A'):
    with f.db.admin_connection() as conn:
        return conn.execute("SELECT p.reserved_krw,p.accounted_krw,p.active_slot,p.stop_latch,t.reserved_krw,t.accounted_krw,t.active_slot "
            "FROM ops.project_budget p JOIN ops.tenant_budgets t USING(budget_id) WHERE p.mode='mock' AND t.tenant_id=%s",(f.tenant_ids[tenant],)).fetchone()

@pytest.mark.parametrize('receipt,end,expected',[(None,'observed',('usage_unknown',False)),(None,'unknown',('usage_unknown',True)),
    (UsageReceipt(1000,100,1100,'gpt-4o-mini','default','synthetic-request'),'observed',('settled',False)),
    (UsageReceipt(1000,100,1100,'gpt-4o-mini','default','synthetic-request'),'unknown',('settled',True))])
def test_reservation_usage_and_remote_end_are_independent(ops_rows,receipt,end,expected):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,__import__('datetime').date(2026,10,1));t=await ticket(f,repo);c=await reserve_dispatch(repo,t)
            assert budget(f)==(Decimal('3.64'),Decimal('0'),1,False,Decimal('3.64'),Decimal('0'),1)
            await repo.settle(t,c,receipt,end)
            with f.db.admin_connection() as conn:
                assert conn.execute('SELECT state,slot_held FROM ops.call_attempts WHERE call_id=%s',(c.call_id,)).fetchone()==expected
                events=conn.execute('SELECT event_kind FROM ops.usage_events WHERE call_id=%s ORDER BY created_at',(c.call_id,)).fetchall()
                assert events==[('reserve',),('settle' if receipt else 'mark_unknown',)]
            expected_cost=Decimal('.51') if receipt else Decimal(0)
            assert budget(f)==(Decimal(0) if receipt else Decimal('3.64'),expected_cost,int(end=='unknown'),False,
                Decimal(0) if receipt else Decimal('3.64'),expected_cost,int(end=='unknown'))
    f.run(check())

def test_same_receipt_noop_conflicting_receipt_latches_stop(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,__import__('datetime').date(2026,10,1));t=await ticket(f,repo);c=await reserve_dispatch(repo,t)
            receipt=UsageReceipt(1000,100,1100,'gpt-4o-mini','default','synthetic-request')
            await repo.settle(t,c,receipt,'observed');before=budget(f)
            assert not (await repo.settle(t,c,receipt,'observed'))['conflict'];assert budget(f)==before
            changed=replace(receipt,input_tokens=1001,total_tokens=1101)
            assert (await repo.settle(t,c,changed,'observed'))['conflict'];assert budget(f)[1]==Decimal('.51') and budget(f)[3]
            with f.db.admin_connection() as conn:
                assert conn.execute("SELECT count(*) FROM ops.usage_events WHERE event_kind='settle'").fetchone()[0]==1
    f.run(check())

@pytest.mark.parametrize('bad',[UsageReceipt(True,0,1,'gpt-4o-mini','default',None),UsageReceipt(1,1,9,'gpt-4o-mini','default',None),
 UsageReceipt(1,0,1,'other-model','default',None),UsageReceipt(1,0,1,'gpt-4o-mini','priority',None)])
def test_invalid_usage_never_zero_settles_and_stops(ops_rows,bad):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,__import__('datetime').date(2026,10,1));t=await ticket(f,repo);c=await reserve_dispatch(repo,t)
            data=await repo.settle(t,c,bad,'observed');assert data['invalid'] and data['state']=='usage_unknown'
            assert budget(f)==(Decimal('3.64'),Decimal(0),0,True,Decimal('3.64'),Decimal(0),0)
    f.run(check())

def test_actual_overrun_is_recorded_not_rejected(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,__import__('datetime').date(2026,10,1));t=await ticket(f,repo);c=await reserve_dispatch(repo,t)
            data=await repo.settle(t,c,UsageReceipt(20000,1000,21000,'gpt-4o-mini','default',None),'observed')
            assert data['state']=='settled' and data['overrun'];assert budget(f)[1]==Decimal('8.64') and budget(f)[3]
    f.run(check())

@pytest.mark.parametrize('mutation',['revoked','membership','revision','account','tenant'])
def test_post_revocation_metering_accepts_only_saved_claim(ops_rows,mutation):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,__import__('datetime').date(2026,10,1));t=await ticket(f,repo);c=await reserve_dispatch(repo,t)
            f.mutate_access(t.ctx,mutation)
            with pytest.raises(ExecutionError):await repo.finish(t,'저장 금지 합성 답변')
            with pytest.raises(ExecutionError):await repo.settle(t,replace(c,claim='forged'),UsageReceipt(1,1,2,'gpt-4o-mini','default',None),'observed')
            await repo.settle(t,c,UsageReceipt(1000,100,1100,'gpt-4o-mini','default',None),'observed')
            assert budget(f)[1]==Decimal('.51')
            with f.db.admin_connection() as conn:assert conn.execute("SELECT count(*) FROM portal.messages WHERE role='assistant'").fetchone()[0]==0
    f.run(check())

@pytest.mark.parametrize('change',['config','disabled','cancel','expired','epoch','stop'])
def test_dispatch_rechecks_and_release_only_unfired(ops_rows,change):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,__import__('datetime').date(2026,10,1));t=await ticket(f,repo)
            call=UUID((await repo.reserve(t,bytes(32)))['call_id'])
            with f.db.admin_connection() as conn:
                if change=='config':conn.execute("UPDATE portal.agent_configs SET config_version=config_version+1 WHERE tenant_id=%s AND agent_key='general'",(t.run.tenant_id,))
                elif change=='disabled':conn.execute("UPDATE portal.agent_configs SET enabled=false WHERE tenant_id=%s AND agent_key='general'",(t.run.tenant_id,))
                elif change=='cancel':conn.execute("UPDATE portal.runs SET state='cancel_requested',revision=revision+1 WHERE run_id=%s",(t.run.run_id,))
                elif change=='expired':pass
                elif change=='epoch':conn.execute('UPDATE portal.runs SET execution_epoch=execution_epoch+1 WHERE run_id=%s',(t.run.run_id,))
                else:conn.execute("UPDATE ops.project_budget SET stopped=true WHERE mode='mock'")
            if change=='expired':await asyncio.sleep(10.1)
            with pytest.raises(ExecutionError):await repo.dispatch(t,call)
            if change=='epoch':assert not await repo.release_unfired(t,call)
            else:
                assert await repo.release_unfired(t,call);assert not await repo.release_unfired(t,call)
                assert budget(f)[:3]==(Decimal(0),Decimal(0),0)
    f.run(check())

def test_last_project_balance_has_one_winner_in_real_concurrent_transactions(ops_rows):
    f=ops_rows
    async def check():
        async with open_web_pool(f.db.runtime_dsn()) as web,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(web,meter,__import__('datetime').date(2026,10,1));a=await ticket(f,repo);b=await ticket(f,repo,'B-U1','B')
            with f.db.admin_connection() as conn:conn.execute("UPDATE ops.project_budget SET operational_cap_krw=3.64 WHERE mode='mock'")
            results=await asyncio.gather(repo.reserve(a,bytes(32)),repo.reserve(b,bytes(32)),return_exceptions=True)
            assert sum(isinstance(x,dict) for x in results)==1
            assert [x.code for x in results if isinstance(x,ExecutionError)]==['QUOTA_EXCEEDED']
            assert budget(f)[:3]==(Decimal('3.64'),Decimal(0),1)
    f.run(check())

def test_duplicate_permit_dispatches_once_and_never_releases_dispatched(ops_rows):
    f=ops_rows
    async def check():
        async with open_web_pool(f.db.runtime_dsn()) as web,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(web,meter,__import__('datetime').date(2026,10,1));t=await ticket(f,repo)
            call=UUID((await repo.reserve(t,bytes(32)))['call_id'])
            assert not (await repo.reserve(t,bytes(32)))['created']
            results=await asyncio.gather(repo.dispatch(t,call),repo.dispatch(t,call))
            assert sum(x is not None for x in results)==1;assert not await repo.release_unfired(t,call)
            assert budget(f)[:3]==(Decimal('3.64'),Decimal(0),1)
    f.run(check())

def test_raw_runtime_cannot_read_claim_or_write_ledger(ops_rows):
    f=ops_rows;f.verify_catalog()
    for role in ('ai_web','ai_meter','ai_index'):
        with f.role_connection(role) as conn:
            for query in ['SELECT worker_claim_hash FROM portal.runs','SELECT dispatch_claim_hash FROM ops.call_attempts',
              'INSERT INTO ops.usage_events DEFAULT VALUES','UPDATE ops.project_budget SET accounted_krw=0','UPDATE ops.call_attempts SET state=state']:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute(query)

@pytest.mark.parametrize('length,valid',[(255,True),(256,True),(257,False)])
def test_provider_request_identifier_ascii_length_boundary(ops_rows,length,valid):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,__import__('datetime').date(2026,10,1));t=await ticket(f,repo);c=await reserve_dispatch(repo,t)
            data=await repo.settle(t,c,UsageReceipt(1000,100,1100,'gpt-4o-mini','default','s'*length),'observed')
            assert data['state']==('settled' if valid else 'usage_unknown') and data['invalid']==(not valid)
    f.run(check())
