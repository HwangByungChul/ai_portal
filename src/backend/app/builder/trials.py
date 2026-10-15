"""Private saved-version trials on the existing worker and central meter."""
from uuid import UUID
from typing import Literal
import psycopg
from psycopg.types.json import Jsonb
from pydantic import Field,BaseModel,ConfigDict,StrictInt,StrictStr,field_validator
from fastapi import APIRouter,Request
from app.builder.schemas import ProfilePreview,compose
from app.builder.repository import BuilderRepository
from app.conversations.repository import ConversationRepository
from app.conversations.routes import digest,CancelRequest
from app.execution.summary_routes import ensure_execution
from app.tenants.routes import context
from app.db import tenant_transaction
from app.ai.token_limits import general_token_count,count_embedding_tokens
from app.errors import AppError,response

router=APIRouter(prefix='/api/v1/admin/builder')
class TrialRequest(ProfilePreview):
    client_send_id:UUID
    purpose:Literal['generate','search']='generate'

class TrialRepository:
    def __init__(self,pool):self.pool=pool
    async def rpc(self,ctx,name,args):
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                return (await (await conn.execute('SELECT security.'+name+'('+','.join(['%s']*len(args))+') AS data',args)).fetchone())['data']
        except (psycopg.Error,ValueError) as error:
            if getattr(error,'sqlstate',None)=='D0404':raise AppError('DOCUMENT_UNAVAILABLE',404) from None
            ConversationRepository.translate(error)
    async def admit(self,ctx,asset,version,body,period,mode,window,trace):
        saved=await BuilderRepository(self.pool).call(ctx,'version',asset,version)
        _,messages=compose(saved['profile'],body['values']);tokens=general_token_count(messages)
        if tokens>6000 or len(messages[-1]['content'])>4000 or (saved['profile']['model_ref']=='default_rules_rag' and count_embedding_tokens(messages[-1]['content'])>4000):raise AppError('TOKEN_LIMIT_EXCEEDED',422)
        data=await self.rpc(ctx,'builder_trial_admit',(ctx.session_id,ctx.tenant_id,asset,version,UUID(str(body['client_send_id'])),Jsonb(body['values']),body['purpose'],period,mode,tokens,window,trace))
        if 'admission_error' in data:raise AppError(data['admission_error'],429,data['retry_after'])
        return data
    async def read(self,ctx,run):
        data=await self.rpc(ctx,'builder_trial_read',(ctx.session_id,ctx.tenant_id,run))
        from app.builder.model_contracts import contract
        return data|{'model_contract':contract(data['model_ref'])}

def valid(request):
    if request.query_params:raise AppError('REQUEST_INVALID',422)
@router.post('/assets/{asset_id}/versions/{version_id}/trials')
async def start(request:Request,asset_id:UUID,version_id:UUID,body:TrialRequest):
    ctx=await context(request,write=True);valid(request);manager=ensure_execution(request);s=request.app.state.settings
    data=await TrialRepository(request.app.state.pool).admit(ctx,asset_id,version_id,body.model_dump(mode='json'),s.budget_period,s.mode,digest(request,ctx,'run_admission'),UUID(request.state.request_id))
    if manager and not data['replayed'] and not data['is_terminal']:manager.notify(ctx,data['run_id'])
    return response(request,{k:data[k] for k in ('run_id','state','revision','replayed')},status_code=200 if data['replayed'] else 201)
@router.get('/trials/{run_id}')
async def read(request:Request,run_id:UUID):
    ctx=await context(request);valid(request);await request.app.state.documents.read_window(ctx)
    return response(request,await TrialRepository(request.app.state.pool).read(ctx,run_id))
@router.post('/trials/{run_id}/cancel')
async def cancel(request:Request,run_id:UUID,body:CancelRequest):
    ctx=await context(request,write=True);valid(request)
    data=await TrialRepository(request.app.state.pool).rpc(ctx,'builder_trial_cancel',(ctx.session_id,ctx.tenant_id,run_id,body.expected_revision,UUID(request.state.request_id)))
    manager=getattr(request.app.state,'execution',None)
    if manager:manager.cancel(ctx,run_id)
    return response(request,data,status_code=200 if data['is_terminal'] else 202)


class ManualAssessment(BaseModel):
    model_config=ConfigDict(extra='forbid')
    client_request_id:UUID
    correctness:StrictInt=Field(ge=1,le=5)
    relevance:StrictInt=Field(ge=1,le=5)
    expected_answer:Literal['answer','insufficient_evidence']
    verdict:Literal['suitable','needs_change','unsuitable']
    comment:StrictStr=Field(max_length=1000)

    @field_validator('comment')
    @classmethod
    def valid_comment(cls,value):
        if '\x00' in value:raise ValueError('REQUEST_INVALID')
        try:value.encode('utf-8')
        except UnicodeError:raise ValueError('REQUEST_INVALID') from None
        return value

@router.get('/assets/{asset_id}/trials')
async def history(request:Request,asset_id:UUID,cursor:UUID|None=None,limit:int=20):
    ctx=await context(request)
    if set(request.query_params)-{'cursor','limit'}:raise AppError('REQUEST_INVALID',422)
    await request.app.state.documents.read_window(ctx)
    data=await TrialRepository(request.app.state.pool).rpc(ctx,'builder_trial_history',(ctx.session_id,ctx.tenant_id,asset_id,cursor,limit))
    return response(request,data)

@router.get('/trials/{run_id}/evidence')
async def evidence(request:Request,run_id:UUID):
    ctx=await context(request);valid(request);await request.app.state.documents.read_window(ctx)
    return response(request,await TrialRepository(request.app.state.pool).rpc(ctx,'builder_trial_evidence',(ctx.session_id,ctx.tenant_id,run_id)))

@router.post('/trials/{run_id}/assessments')
async def assess(request:Request,run_id:UUID,body:ManualAssessment):
    ctx=await context(request,write=True);valid(request)
    data=await TrialRepository(request.app.state.pool).rpc(ctx,'builder_trial_assess',(ctx.session_id,ctx.tenant_id,run_id,body.client_request_id,Jsonb(body.model_dump(exclude={'client_request_id'}))))
    return response(request,data,status_code=200 if data['replayed'] else 201)

class TrialComparison(BaseModel):
    model_config=ConfigDict(extra='forbid')
    left:UUID
    right:UUID

@router.post('/trial-comparisons')
async def compare(request:Request,body:TrialComparison):
    ctx=await context(request,write=True);valid(request);await request.app.state.documents.read_window(ctx)
    return response(request,await TrialRepository(request.app.state.pool).rpc(ctx,'builder_trial_compare',(ctx.session_id,ctx.tenant_id,body.left,body.right)))
