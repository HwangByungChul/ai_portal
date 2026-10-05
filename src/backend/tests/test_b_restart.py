from datetime import date
from uuid import UUID
from decimal import Decimal
import pytest
from app.ai.repository import CallRepository
from app.ai.types import UsageReceipt
from app.ai.providers import MockProvider
from app.execution.manager import ExecutionManager
from app.execution.stream import StreamHub
from app.db import open_web_pool,open_meter_pool
from test_operations import ops_rows
from test_ai_ledger import ticket,reserve_dispatch,budget

@pytest.mark.parametrize('phase',['accepted','reserved','dispatched','settled_unknown_end','failed_reserved','failed_dispatched'])
def test_recovery_uses_metadata_only_and_never_replays_provider(ops_rows,phase):
    f=ops_rows
    async def check():
        async with open_web_pool(f.db.runtime_dsn()) as web,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(web,meter,date(2026,10,1));claim=None
            if phase=='accepted':
                from types import SimpleNamespace
                from test_execution import submit
                ctx,run=await submit(f,repo);t=SimpleNamespace(ctx=ctx,run=SimpleNamespace(tenant_id=ctx.tenant_id,run_id=run))
            else:t=await ticket(f,repo)
            if phase in ('reserved','failed_reserved'):await repo.reserve(t,bytes(32))
            elif phase in ('dispatched','failed_dispatched','settled_unknown_end'):claim=await reserve_dispatch(repo,t)
            if phase=='settled_unknown_end':await repo.settle(t,claim,UsageReceipt(1000,100,1100,'gpt-4o-mini','default',None),'unknown')
            if phase.startswith('failed_'):await repo.fail(t,'LEDGER_UNAVAILABLE')
            f.mutate_access(t.ctx,'revoked')
            manager=ExecutionManager(repo,MockProvider(),'mock',StreamHub());await manager.start()
            assert manager.recovery=={'interrupted':0 if phase.startswith('failed_') else 1,'released_unfired':int(phase in ('reserved','failed_reserved')),'unknown_dispatched':int(phase in ('dispatched','failed_dispatched'))}
            assert not manager.tasks and not manager.hub.drafts
            with f.db.admin_connection() as conn:
                assert conn.execute('SELECT state,execution_epoch FROM portal.runs').fetchone()==(('failed',1) if phase.startswith('failed_') else ('interrupted',2))
                assert conn.execute("SELECT count(*) FROM portal.messages WHERE role='assistant'").fetchone()[0]==0
            if phase in ('reserved','failed_reserved'):assert budget(f)[:3]==(Decimal(0),Decimal(0),0)
            elif phase in ('dispatched','failed_dispatched'):assert budget(f)[:3]==(Decimal('3.64'),Decimal(0),1)
            elif phase=='settled_unknown_end':assert budget(f)[:3]==(Decimal(0),Decimal('.51'),1)
            if claim is not None:
                # A receipt from the original dispatch remains legitimate even after run epoch/authority changes.
                await repo.settle(t,claim,UsageReceipt(1000,100,1100,'gpt-4o-mini','default',None),'observed')
                assert budget(f)[:3]==(Decimal(0),Decimal('.51'),0)
            await manager.close()
    f.run(check())
