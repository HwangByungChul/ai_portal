from dataclasses import dataclass,field
from uuid import UUID
from psycopg.types.json import Jsonb
from app.ai.repository import ExecutionError
from app.ai.rag_gateway import generation
from app.ai.token_limits import general_token_count,encoding
from app.db import tenant_transaction
from app.errors import AppError
from app.execution.summary_repository import SummaryRepository,messages,EMPTY
from app.policies.document_summary import require_summary_policy
from common_core.ai_pipeline.summary.selection import validate_selection
from common_core.ai_pipeline.summary.render import render_extracts

@dataclass(frozen=True)
class SummaryResult:
    body:str=field(repr=False)
    evidence:tuple=field(repr=False)
    answer_kind:str

class SummaryExecutor:
    def __init__(self,repository,documents,provider):self.repository=repository;self.summary=SummaryRepository(documents);self.provider=provider;self.stop_latch=False
    async def execute(self,ticket):
        try:
            if self.stop_latch:raise ExecutionError('PROJECT_STOPPED')
            request=await self.summary.request(ticket.ctx,ticket.run.run_id)
            async with tenant_transaction(self.summary.pool,ticket.ctx) as conn:
                await conn.execute('SELECT security.summary_source_guard(%s,%s,%s)',(ticket.ctx.session_id,ticket.ctx.tenant_id,ticket.run.run_id))
                row,candidates=await self.summary.source(ticket.ctx,request['document_ref'],ticket.run.mode,conn)
                if [{k:v for k,v in x.evidence.items() if k!='quote'} for x in candidates]!=request['candidates']:raise ExecutionError('SUMMARY_OUTPUT_INVALID')
            if not candidates:
                require_summary_policy(row['title'],EMPTY);return SummaryResult(EMPTY,(),'insufficient_evidence')
            msg=messages(row['title'],candidates,request['bullet_count'])
            if general_token_count(msg)>6000:raise ExecutionError('SUMMARY_LIMIT_EXCEEDED')
            sources=({k:candidates[0].evidence[k] for k in ('source_tenant_id','document_id','version_id','index_id')},)
            outcome=await generation(self.repository,self.provider,ticket,sources,msg)
            if outcome.safe_error_code or outcome.body is None:
                if outcome.safe_error_code in ('LEDGER_UNAVAILABLE','LEDGER_CONFLICT','USAGE_INVALID','PROJECT_STOPPED'):self.stop_latch=True
                raise ExecutionError(outcome.safe_error_code or 'PROVIDER_ERROR')
            if len(encoding('o200k_base').encode(outcome.body,disallowed_special=()))>512:raise ExecutionError('SUMMARY_OUTPUT_INVALID')
            ids=validate_selection(outcome.body,tuple(x.candidate_id for x in candidates),request['bullet_count'])
            selected=tuple(x for x in candidates if x.candidate_id in ids);body=render_extracts(tuple(x.quote for x in selected)) if selected else EMPTY
            require_summary_policy(row['title'],body)
            return SummaryResult(body,tuple(x.evidence for x in selected),'answer' if selected else 'insufficient_evidence')
        except AppError as error:raise ExecutionError('EXECUTION_BLOCKED' if error.status in (401,403,404) else error.code) from None
        except ValueError:raise ExecutionError('SUMMARY_OUTPUT_INVALID') from None
    async def finish(self,ticket,result):
        try:
            # Re-read the immutable original and evaluate current policy immediately before sealing.
            request=await self.summary.request(ticket.ctx,ticket.run.run_id)
            async with tenant_transaction(self.summary.pool,ticket.ctx) as conn:
                row,candidates=await self.summary.source(ticket.ctx,request['document_ref'],ticket.run.mode,conn)
                require_summary_policy(row['title'],result.body)
            return await self.repository._rpc(self.repository.web_pool,'summary_finish',(*self.repository.worker_args(ticket),result.body,result.answer_kind,Jsonb(list(result.evidence))),ticket.ctx)
        except AppError as error:raise ExecutionError('EXECUTION_BLOCKED' if error.status in (401,403,404) else error.code) from None
    async def close(self):await self.provider.close()
