"""One confirmed permit precedes one provider invocation; no transaction spans I/O."""
import asyncio
import hashlib
import json
from uuid import UUID
from app.ai.types import ProviderOutcome
from app.ai.pricing import cost_krw
from app.ai.repository import ExecutionError,DispatchUncertain

class AiGateway:
    def __init__(self,repository,provider=None,*,router=None,guardrails=None):
        self.repository=repository;self.provider=provider;self.router=router;self.guardrails=guardrails;self.stop_latch=False

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
        provider=self.provider
        if self.router is not None:
            model_id=getattr(ticket,'model_id',None)
            try:_,provider=self.router.route(model_id)
            except Exception:return ProviderOutcome(None,None,'unknown','MODEL_NOT_PERMITTED')
        if provider is None:return ProviderOutcome(None,None,'unknown','PROVIDER_ERROR')
        policy_before=None
        if self.guardrails is not None:
            try:policy_before=await self.guardrails.snapshot(ticket.ctx)
            except Exception:return ProviderOutcome(None,None,'unknown','STORAGE_UNAVAILABLE')
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
            # Provider deltas are private. Callers receive only the inspected,
            # persisted result through the execution manager, never raw chunks.
            output_bytes=0
            async def private_delta(text):
                nonlocal output_bytes
                if not isinstance(text,str):raise ExecutionError('OUTPUT_INVALID')
                output_bytes+=len(text.encode('utf-8'))
                if output_bytes>32768:raise ExecutionError('PAYLOAD_TOO_LARGE')
            try:outcome=await provider.generate(claim,ticket.messages,private_delta)
            except asyncio.CancelledError:
                outcome=ProviderOutcome(None,None,'unknown','EXECUTION_INTERRUPTED')
            except Exception as error:outcome=ProviderOutcome(None,None,'unknown',error.code if isinstance(error,ExecutionError) else 'PROVIDER_ERROR')
            if outcome.body is not None:
                try:
                    if not isinstance(outcome.body,str):raise ValueError('OUTPUT_INVALID')
                    body_bytes=len(outcome.body.encode('utf-8'))
                except (ValueError,UnicodeError):
                    outcome=ProviderOutcome(None,outcome.receipt,outcome.end_status,'OUTPUT_INVALID')
                else:
                    if body_bytes>32768:outcome=ProviderOutcome(None,outcome.receipt,outcome.end_status,'PAYLOAD_TOO_LARGE')
            if outcome.body is not None:
                from app.guardrails.engine import evaluate_output,text_hash
                from app.guardrails.routes import record_violation
                t_run=getattr(ticket,'run',None);t_ctx=getattr(ticket,'ctx',None)
                tid=str(getattr(t_run,'tenant_id',''));uid=str(getattr(t_ctx,'user_id',''))
                if self.guardrails is not None:
                    try:
                        out_res=await self.guardrails.inspect(ticket.ctx,outcome.body,direction='output',
                            run_id=getattr(t_run,'run_id',None),trace_id=getattr(ticket,'trace_id',None),previous=policy_before)
                    except Exception:
                        outcome=ProviderOutcome(None,outcome.receipt,outcome.end_status,'STORAGE_UNAVAILABLE')
                        code=await self._meter(ticket,claim,outcome)
                        return ProviderOutcome(None,outcome.receipt,outcome.end_status,code or 'STORAGE_UNAVAILABLE')
                else:out_res=evaluate_output(outcome.body)
                if out_res.action=='block':
                    if self.guardrails is None:record_violation(tid,uid,'output',out_res.rule_ids,text_hash(outcome.body),out_res.revision)
                    outcome=ProviderOutcome(None,outcome.receipt,outcome.end_status,'GUARDRAIL_OUTPUT_BLOCKED')
                elif out_res.action=='mask' and out_res.masked_text is not None:
                    if self.guardrails is None:record_violation(tid,uid,'output',out_res.rule_ids,text_hash(outcome.body),out_res.revision)
                    outcome=ProviderOutcome(out_res.masked_text,outcome.receipt,outcome.end_status,outcome.safe_error_code)
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
