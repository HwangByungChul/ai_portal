"""Approved Agent execution through the existing dispatcher and usage ledger."""
import psycopg
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Request
from pydantic import BaseModel,ConfigDict,StrictInt,Field
from psycopg.types.json import Jsonb
from app.builder.schemas import ProfilePreview,compose
from app.builder.trials import TrialRepository
from app.ai.token_limits import general_token_count,count_embedding_tokens
from app.conversations.routes import digest,CancelRequest
from app.conversations.repository import ConversationRepository
from app.tenants.routes import context
from app.execution.summary_routes import ensure_execution
from app.operations.routes import apply_agent_readiness
from app.errors import AppError,response

router=APIRouter(prefix='/api/v1')
class PublishedRun(ProfilePreview):
    client_send_id:UUID
    version_id:UUID
    expected_publication_revision:StrictInt=Field(ge=0,le=9223372036854775806)
class DynamicFavoriteRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    client_request_id:UUID
    expected_revision:StrictInt=Field(ge=0,le=9223372036854775806)
    active:bool

class PublishedRepository(TrialRepository):
    async def rpc(self,ctx,name,args):
        try:return await super().rpc(ctx,name,args)
        except psycopg.Error as error:
            if error.sqlstate=='B0401':raise AppError('NOT_FOUND',404) from None
            raise

    async def asset(self,ctx,asset,mode):
        return await self.rpc(ctx,'published_asset_guard',(ctx.session_id,ctx.tenant_id,asset,mode))
    async def read(self,ctx,run):
        return await self.rpc(ctx,'published_agent_read',(ctx.session_id,ctx.tenant_id,'run',run,Jsonb({}),'mock'))
    async def admit(self,ctx,asset,body,period,mode,window,trace):
        pub=await self.asset(ctx,asset,mode)
        if pub['publication_revision']!=body['expected_publication_revision'] or pub['version_id']!=str(body['version_id']):raise AppError('REVISION_CONFLICT',409)
        _,messages=compose(pub['profile'],body['values']);tokens=general_token_count(messages)
        if tokens>6000 or len(messages[-1]['content'])>4000 or (pub['config']['execution_kind']=='rules_rag' and count_embedding_tokens(messages[-1]['content'])>4000):raise AppError('TOKEN_LIMIT_EXCEEDED',422)
        return await self.rpc(ctx,'published_agent_admit',(ctx.session_id,ctx.tenant_id,asset,UUID(str(body['version_id'])),body['client_send_id'],Jsonb(body['values']),'generate',body['expected_publication_revision'],period,mode,tokens,window,trace))

    async def favorite(self,ctx,asset,active,expected_revision,client_request_id,trace=None):
        return await self.rpc(ctx,'dynamic_favorite_mutate',(ctx.session_id,trace or client_request_id,ctx.tenant_id,asset,client_request_id,Jsonb({'expected_revision':expected_revision,'active':active})))

async def read_call(request,action,target=None,body=None,query=False,allowed=None):
    ctx=await context(request);params=request.query_params
    valid_keys=set(allowed) if allowed is not None else ({'cursor'} if query else set())
    if (set(params)-valid_keys) or any(len(params.getlist(k))!=1 for k in params):raise AppError('REQUEST_INVALID',422)
    await request.app.state.documents.read_window(ctx)
    if action=='run':
        meetings=getattr(request.app.state,'use_case_execution',None)
        if meetings is not None:
            await meetings.meetings.guard_child(ctx,target)
    data=await PublishedRepository(request.app.state.pool).rpc(ctx,'published_agent_read',(ctx.session_id,ctx.tenant_id,action,target,Jsonb(body or {}),request.app.state.settings.mode))
    if action=='list':await apply_agent_readiness(request,ctx,data)
    elif action=='detail':await apply_agent_readiness(request,ctx,{'items':[data]})
    return response(request,data)
@router.get('/published-agents')
async def listing(request:Request,cursor:UUID|None=None,mine:bool|None=False):
    body={}
    if cursor:body['cursor']=str(cursor)
    if mine:body['mine']=True
    return await read_call(request,'list',body=body,query=True,allowed={'cursor','mine'})
@router.get('/published-agents/{asset_id}')
async def asset(request:Request,asset_id:UUID):return await read_call(request,'detail',asset_id)
@router.put('/published-agents/{asset_id}/favorite')
async def set_favorite(request:Request,asset_id:UUID,body:DynamicFavoriteRequest):
    ctx=await context(request,write=True)
    if request.query_params:raise AppError('REQUEST_INVALID',422)
    data=await PublishedRepository(request.app.state.pool).favorite(
        ctx,asset_id,body.active,body.expected_revision,body.client_request_id,UUID(request.state.request_id)
    )
    return response(request,data)
@router.get('/published-agents/{asset_id}/runs')
async def history(request:Request,asset_id:UUID,cursor:UUID|None=None):return await read_call(request,'history',asset_id,{'cursor':str(cursor)} if cursor else {},query=True)
@router.post('/published-agents/{asset_id}/runs')
async def start(request:Request,asset_id:UUID,body:PublishedRun):
    ctx=await context(request,write=True)
    if request.query_params:raise AppError('REQUEST_INVALID',422)
    manager=ensure_execution(request);s=request.app.state.settings
    data=await PublishedRepository(request.app.state.pool).admit(ctx,asset_id,body.model_dump(),s.budget_period,s.mode,digest(request,ctx,'run_admission'),UUID(request.state.request_id))
    if 'admission_error' in data:raise AppError(data['admission_error'],429,data['retry_after'])
    if manager and not data['replayed'] and not data['is_terminal']:manager.notify(ctx,data['run_id'])
    return response(request,data,status_code=200 if data['replayed'] else 202)
async def history_call(request,action,target=None,body=None,allowed=()):
    ctx=await context(request);params=request.query_params
    if set(params)-set(allowed) or any(len(params.getlist(k))!=1 for k in params):raise AppError('REQUEST_INVALID',422)
    await request.app.state.documents.read_window(ctx)
    data=await PublishedRepository(request.app.state.pool).rpc(ctx,'published_run_history',(ctx.session_id,ctx.tenant_id,action,target,Jsonb(body or {}),request.app.state.settings.mode))
    return response(request,data)
@router.get('/published-agent-runs')
async def all_history(request:Request,cursor:UUID|None=None,asset_id:UUID|None=None,state:Literal['accepted','running','cancel_requested','completed','cancelled','failed','blocked','interrupted']|None=None):
    body={k:str(v) for k,v in {'cursor':cursor,'asset_id':asset_id,'state':state}.items() if v is not None}
    return await history_call(request,'list',body=body,allowed=('cursor','asset_id','state'))
@router.get('/published-agent-runs/{run_id}/record')
async def history_record(request:Request,run_id:UUID):return await history_call(request,'record',run_id)
@router.get('/published-agent-runs/{run_id}')
async def run(request:Request,run_id:UUID):return await read_call(request,'run',run_id)
@router.post('/published-agent-runs/{run_id}/cancel')
async def cancel(request:Request,run_id:UUID,body:CancelRequest):
    ctx=await context(request,write=True)
    if request.query_params:raise AppError('REQUEST_INVALID',422)
    repo=PublishedRepository(request.app.state.pool)
    # Only own dynamic runs can enter this route; cancellation remains possible after retirement/ACL withdrawal.
    await repo.rpc(ctx,'published_run_history',(ctx.session_id,ctx.tenant_id,'record',run_id,Jsonb({}),request.app.state.settings.mode))
    data=await ConversationRepository(repo.pool).cancel(ctx,run_id,body.expected_revision,UUID(request.state.request_id))
    manager=getattr(request.app.state,'execution',None)
    if manager:manager.cancel(ctx,run_id)
    return response(request,data,status_code=200 if data['is_terminal'] else 202)
