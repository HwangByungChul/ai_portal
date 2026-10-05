"""One confirmed permit precedes one provider invocation; no transaction spans I/O."""
import asyncio
import hashlib
import json
from uuid import UUID
from app.ai.types import ProviderOutcome
from app.ai.pricing import cost_krw
from app.ai.repository import ExecutionError,DispatchUncertain

class AiGateway:
    def __init__(self,repository,provider):
        self.repository=repository;self.provider=provider;self.stop_latch=False

    async def _meter(self,ticket,claim,outcome):
        invalid=outcome.safe_error_code=='USAGE_INVALID';receipt=outcome.receipt
        if receipt is not None:
            try:cost_krw(receipt)
            except (ValueError,TypeError):receipt=None;invalid=True
        for attempt in range(2):
            try:
                data=await self.repository.settle(ticket,claim,receipt,outcome.end_status,invalid)
                if data['conflict'] or data['invalid'] or data['overrun']:
                    self.stop_latch=True
                    return 'LEDGER_CONFLICT' if data['conflict'] else 'USAGE_INVALID' if data['invalid'] else 'PROJECT_STOPPED'
                return None
            except ExecutionError:
                if attempt==1:self.stop_latch=True;return 'LEDGER_UNAVAILABLE'
                await asyncio.sleep(0)

    async def execute(self,ticket,on_delta):
        if self.stop_latch:return ProviderOutcome(None,None,'unknown','PROJECT_STOPPED')
        fingerprint=hashlib.sha256(json.dumps(ticket.messages,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).digest()
        call_id=None;claim=None
        try:
            deadline=asyncio.get_running_loop().time()+5
            while True:
                try:
                    data=await self.repository.reserve(ticket,fingerprint);break
                except ExecutionError as error:
                    if error.code!='CAPACITY_BUSY' or asyncio.get_running_loop().time()>=deadline:raise
                    await asyncio.sleep(0.1)
            call_id=UUID(data['call_id'])
            if not data['created']:return ProviderOutcome(None,None,'unknown','EXECUTION_BLOCKED')
            claim=await self.repository.dispatch(ticket,call_id)
            if claim is None:return ProviderOutcome(None,None,'unknown','EXECUTION_BLOCKED')
            try:outcome=await self.provider.generate(claim,ticket.messages,on_delta)
            except asyncio.CancelledError:
                outcome=ProviderOutcome(None,None,'unknown','EXECUTION_INTERRUPTED')
            except Exception as error:outcome=ProviderOutcome(None,None,'unknown',error.code if isinstance(error,ExecutionError) else 'PROVIDER_ERROR')
            code=await self._meter(ticket,claim,outcome)
            if code:return ProviderOutcome(None,outcome.receipt,outcome.end_status,code)
            return outcome
        except DispatchUncertain as error:
            claim=error.claim
            await self._meter(ticket,claim,ProviderOutcome(None,None,'unknown','LEDGER_UNAVAILABLE'))
            self.stop_latch=True
            return ProviderOutcome(None,None,'unknown','LEDGER_UNAVAILABLE')
        except ExecutionError as error:
            return ProviderOutcome(None,None,'unknown',error.code)
        finally:
            if call_id is not None and claim is None:
                try:await self.repository.release_unfired(ticket,call_id)
                except ExecutionError:self.stop_latch=True
