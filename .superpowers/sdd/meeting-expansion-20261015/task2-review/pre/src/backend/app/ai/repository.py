"""Fixed SQL capabilities only; metering never borrows a content connection."""
from dataclasses import dataclass,field,asdict
import asyncio
import hashlib
import secrets
from uuid import UUID
import psycopg
from psycopg.types.json import Jsonb
from app.ai.types import VerifiedRun,DispatchClaim
from app.db import tenant_transaction

class ExecutionError(RuntimeError):
    def __init__(self,code):self.code=code;super().__init__(code)

class DispatchUncertain(ExecutionError):
    def __init__(self,claim):
        super().__init__('LEDGER_UNAVAILABLE');self.claim=claim

CODES={'D0404':'EXECUTION_BLOCKED','B0340':'EXECUTION_BLOCKED','B0401':'EXECUTION_BLOCKED','B0402':'AGENT_DISABLED','B0403':'CONFIG_CHANGED',
 'B0404':'EXECUTION_BLOCKED','B0405':'PROJECT_STOPPED','B0406':'EXECUTION_BLOCKED',
 'B0407':'PERMIT_EXPIRED','B0410':'EXECUTION_BLOCKED','B0411':'EXECUTION_BLOCKED',
 'B0430':'QUOTA_EXCEEDED','B0431':'CAPACITY_BUSY','A0401':'EXECUTION_BLOCKED','A0403':'EXECUTION_BLOCKED','A0404':'EXECUTION_BLOCKED'}

def digest(value):return hashlib.sha256(value.encode('ascii')).digest()

@dataclass(frozen=True)
class RunAssetBinding:
    asset_id:UUID
    revision:int
    version_id:UUID
    config_hash:str

@dataclass(frozen=True)
class RunTicket:
    ctx:object=field(repr=False)
    run:VerifiedRun
    worker:str=field(repr=False)
    messages:list=field(repr=False)
    agent:str="general"
    document_refs:tuple=()
    task_kind:str="chat"
    asset_binding:RunAssetBinding|None=None
    model_id:str|None=None

class CallRepository:
    def __init__(self,web_pool,meter_pool,period):
        self.web_pool=web_pool;self.meter_pool=meter_pool;self.period=period

    async def _rpc(self,pool,name,args,ctx=None):
        try:
            if ctx is not None:
                async with tenant_transaction(pool,ctx) as conn:
                    row=await (await conn.execute('SELECT security.'+name+'('+','.join(['%s']*len(args))+') AS data',args)).fetchone()
            else:
                async with pool.connection() as conn:
                    async with conn.transaction():
                        row=await (await conn.execute('SELECT security.'+name+'('+','.join(['%s']*len(args))+') AS data',args)).fetchone()
            return row['data']
        except (psycopg.Error,ValueError) as error:
            if ctx is not None and isinstance(error,ValueError) and error.args==('CONTEXT_UNAVAILABLE',):raise ExecutionError('EXECUTION_BLOCKED') from None
            code='SUMMARY_OUTPUT_INVALID' if name=='summary_finish' and getattr(error,'sqlstate',None)=='A0422' else CODES.get(getattr(error,'sqlstate',None),'LEDGER_UNAVAILABLE')
            raise ExecutionError(code) from None

    async def claim(self,ctx,run_id,mode):
        worker=secrets.token_urlsafe(32)
        try:
            async with tenant_transaction(self.web_pool,ctx) as conn:
                row=await (await conn.execute('SELECT task_kind,asset_id,asset_revision,asset_version_id,asset_config_hash FROM portal.runs WHERE tenant_id=%s AND run_id=%s',(ctx.tenant_id,run_id))).fetchone()
        except ValueError as error:
            if error.args==('CONTEXT_UNAVAILABLE',):raise ExecutionError('EXECUTION_BLOCKED') from None
            raise
        capability='summary_claim' if row and row['task_kind']=='document_summary' else 'execution_claim'
        data=await self._rpc(self.web_pool,capability,(ctx.session_id,ctx.tenant_id,run_id,mode,self.period,digest(worker)),ctx)
        if data is None:return None
        v=VerifiedRun(*(UUID(data[k]) for k in ('tenant_id','run_id','owner_user_id','origin_session_id')),
            data['epoch'],data['config_revision'],data['mode'])
        binding=RunAssetBinding(row['asset_id'],row['asset_revision'],row['asset_version_id'],row['asset_config_hash']) if row and row['asset_id'] is not None else None
        if data.get('trial_binding') or data.get('published_binding'):
            sealed=data.get('trial_binding') or data['published_binding'];binding=RunAssetBinding(UUID(sealed['asset_id']),sealed['revision'],UUID(sealed['version_id']),sealed['config_hash'])
        if binding is not None and data.get('task_kind') not in ('builder_trial','asset_chat') and binding.revision!=v.config_revision:raise ExecutionError('EXECUTION_BLOCKED')
        return RunTicket(ctx,v,worker,data['messages'],data.get('agent_key','general'),tuple(data.get('document_refs') or ()),data.get('task_kind','chat'),binding)

    def worker_args(self,ticket):
        v=ticket.run;return (v.origin_session_id,v.tenant_id,v.run_id,v.epoch,digest(ticket.worker))

    async def reserve(self,ticket,input_fingerprint):
        return await self._rpc(self.web_pool,'call_reserve',(*self.worker_args(ticket),self.period,input_fingerprint),ticket.ctx)

    async def dispatch(self,ticket,call_id):
        secret=secrets.token_urlsafe(32);claim=DispatchClaim(call_id,ticket.run.epoch,secret)
        # Only confirmed successful commit returns a usable dispatch capability.
        try:ok=await self._rpc(self.web_pool,'call_dispatch',(*self.worker_args(ticket),call_id,digest(secret)),ticket.ctx)
        except (ExecutionError,asyncio.CancelledError) as error:
            if isinstance(error,asyncio.CancelledError) or error.code=='LEDGER_UNAVAILABLE':raise DispatchUncertain(claim) from None
            raise
        return claim if ok else None

    async def release_unfired(self,ticket,call_id):
        v=ticket.run
        return await self._rpc(self.web_pool,'call_release',(v.tenant_id,v.run_id,v.epoch,digest(ticket.worker),call_id))

    async def settle(self,ticket,claim,receipt,end_status,invalid=False):
        return await self._rpc(self.meter_pool,'call_meter',(ticket.run.tenant_id,claim.call_id,claim.epoch,digest(claim.claim),
            Jsonb(asdict(receipt)) if receipt is not None else None,end_status,invalid))

    async def mark_unknown(self,ticket,claim,end_status='unknown',invalid=False):
        return await self.settle(ticket,claim,None,end_status,invalid)

    async def heartbeat(self,ticket):
        return await self._rpc(self.web_pool,'execution_heartbeat',self.worker_args(ticket),ticket.ctx)

    async def finish(self,ticket,body):
        return await self._rpc(self.web_pool,'execution_finish',(*self.worker_args(ticket),body),ticket.ctx)

    async def fail(self,ticket,code):
        v=ticket.run
        return await self._rpc(self.web_pool,'execution_fail',(v.tenant_id,v.run_id,v.epoch,digest(ticket.worker),code))

    async def readiness(self,ctx,mode):
        return await self._rpc(self.web_pool,'execution_readiness',(ctx.session_id,ctx.tenant_id,self.period,mode),ctx)

    async def reject(self,ctx,run_id,mode,code):
        return await self._rpc(self.web_pool,'execution_reject',(ctx.session_id,ctx.tenant_id,ctx.user_id,run_id,mode,code))

    async def stream_view(self,ctx,run_id,mode):
        return await self._rpc(self.web_pool,'execution_stream_view',(ctx.session_id,ctx.tenant_id,run_id,mode,self.period),ctx)
