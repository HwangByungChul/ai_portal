"""Run-bound query embedding and strict fact selection on the existing central meter."""
import asyncio,hashlib,json,secrets
from dataclasses import asdict
from uuid import UUID
from psycopg.types.json import Jsonb
from app.ai.repository import CallRepository,ExecutionError,DispatchUncertain,digest
from app.ai.gateway import AiGateway
from app.ai.types import DispatchClaim,ProviderOutcome
from app.ai.pricing import cost_krw
from app.ai.token_limits import count_embedding_tokens,general_token_count
from app.documents.embedding import vector_values

class RagCallRepository(CallRepository):
    def __init__(self,repository,operation,sources):
        super().__init__(repository.web_pool,repository.meter_pool,repository.period);self.operation=operation;self.sources=sources
    async def reserve(self,ticket,fingerprint):
        return await self._rpc(self.web_pool,'rag_call_reserve',(*self.worker_args(ticket),self.period,fingerprint,self.operation,Jsonb(list(self.sources))),ticket.ctx)

class QueryGateway:
    def __init__(self,repository,provider):self.repository=repository;self.provider=provider;self.stop_latch=False
    async def execute(self,ticket,prompt,sources):
        if self.stop_latch:raise ExecutionError('PROJECT_STOPPED')
        tokens=count_embedding_tokens(prompt)
        if tokens>4000:raise ExecutionError('TOKEN_LIMIT_EXCEEDED')
        repo=RagCallRepository(self.repository,'embed_query',sources);fingerprint=hashlib.sha256(prompt.encode()).digest();call=None;claim=None
        try:
            data=await repo.reserve(ticket,fingerprint);call=UUID(data['call_id'])
            if not data['created']:raise ExecutionError('EXECUTION_BLOCKED')
            claim=await repo.dispatch(ticket,call)
            if claim is None:raise ExecutionError('EXECUTION_BLOCKED')
            try:
                async with asyncio.timeout(60):values,receipt=await self.provider.embed(claim.call_id,[prompt],tokens)
                vector=vector_values(values,1)[0];cost_krw(receipt)
                status=await repo.settle(ticket,claim,receipt,'observed')
                if status['state']!='settled' or status['invalid'] or status['conflict'] or status['overrun']:raise ExecutionError('LEDGER_UNAVAILABLE')
                return vector
            except BaseException:
                try:await repo.mark_unknown(ticket,claim)
                except BaseException:self.stop_latch=True
                raise
        except DispatchUncertain as error:
            self.stop_latch=True
            try:await repo.mark_unknown(ticket,error.claim)
            except BaseException:pass
            raise ExecutionError('LEDGER_UNAVAILABLE') from None
        finally:
            if call is not None and claim is None:
                try:await repo.release_unfired(ticket,call)
                except ExecutionError:self.stop_latch=True

async def generation(repository,provider,ticket,sources,messages):
    repo=RagCallRepository(repository,'generate_rag',sources);gateway=AiGateway(repo,provider)
    from dataclasses import replace
    async def buffer_only(text):pass
    return await gateway.execute(replace(ticket,messages=messages),buffer_only)
