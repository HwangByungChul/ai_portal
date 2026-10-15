"""Buffered private trial output; reuse confirmed dispatch, metering and source verification."""
from psycopg.types.json import Jsonb
from app.ai.repository import ExecutionError
from app.builder.trials import TrialRepository
from app.assets.published import PublishedRepository
from app.errors import AppError

class TrialExecutor:
    def __init__(self,repository,gateway,rag):self.repository=repository;self.gateway=gateway;self.rag=rag
    async def execute(self,ticket):
        try:
            data=await (PublishedRepository(self.repository.web_pool) if ticket.task_kind=='asset_chat' else TrialRepository(self.repository.web_pool)).read(ticket.ctx,ticket.run.run_id)
            if ticket.task_kind=='asset_chat':data=data|{'purpose':'generate'}
            model_ref=data.get('model_ref')
            if model_ref:
                if self.gateway.router is not None:self.gateway.router.route(model_ref)
                from dataclasses import replace
                ticket=replace(ticket,model_id=model_ref)
            if ticket.agent=='rules_rag':
                if self.rag is None:raise ExecutionError('FEATURE_NOT_READY')
                if data['purpose']=='search':
                    if not ticket.document_refs:return {'kind':'retrieval','candidates':[],'answer_kind':'insufficient_evidence','reason':'empty_scope'}
                    sources=await self.rag.search.allowed(ticket.ctx,ticket.document_refs,ticket.run.mode)
                    vector=await self.rag.query.execute(ticket,ticket.messages[-1]['content'],sources)
                    packets,_=await self.rag.search.packets(ticket.ctx,ticket.messages[-1]['content'],ticket.run.mode,sources,vector)
                    await self.rag.search.guard(ticket.ctx,ticket.run.mode,sources)
                    return {'kind':'retrieval','candidates':[p.public()|{'source':{k:p.evidence[k] for k in ('source_tenant_id','document_id','version_id','index_id')}} for p in packets],'answer_kind':'answer' if packets else 'insufficient_evidence','reason':None if packets else 'no_matching_evidence'}
                result=await self.rag.execute(ticket)
                return {'kind':'generation','text':result.body,'evidence':list(result.evidence),'answer_kind':result.answer_kind}
            async def buffered(text):
                if not await self.repository.heartbeat(ticket):raise ExecutionError('EXECUTION_BLOCKED')
            outcome=await self.gateway.execute(ticket,buffered)
            if outcome.safe_error_code or outcome.body is None:raise ExecutionError(outcome.safe_error_code or 'PROVIDER_ERROR')
            return {'kind':'generation','text':outcome.body,'evidence':[],'answer_kind':'answer'}
        except AppError as error:raise ExecutionError('EXECUTION_BLOCKED' if error.status in (401,403,404,409) or error.code=='DOCUMENT_UNAVAILABLE' else error.code) from None
    async def finish(self,ticket,result):
        return await self.repository._rpc(self.repository.web_pool,'published_agent_finish' if ticket.task_kind=='asset_chat' else 'builder_trial_finish',(*self.repository.worker_args(ticket),Jsonb(result)),ticket.ctx)
