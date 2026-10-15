from uuid import UUID
from typing import Literal
from fastapi import APIRouter,Request
from pydantic import BaseModel,ConfigDict,StrictBool,StrictInt,StrictStr,Field,field_validator,model_validator
from app.builder.shares import ShareRepository
from psycopg.types.json import Jsonb
from app.tenants.routes import context
from app.errors import AppError,response

router=APIRouter(prefix='/api/v1/admin/asset-deployments')
class DeploymentRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    client_request_id:UUID
    share_id:UUID
    expected_publication_revision:StrictInt=Field(ge=0,le=9223372036854775806)
    reason:StrictStr=Field(min_length=1,max_length=500)
    audience:Literal['all','restricted']
    member_ids:list[UUID]=Field(max_length=200)
    @field_validator('reason')
    @classmethod
    def text(cls,v):
        if not v.strip() or '\x00' in v:raise ValueError('REQUEST_INVALID')
        v.encode('utf-8');return v
    @model_validator(mode='after')
    def members(self):
        if len(set(self.member_ids))!=len(self.member_ids) or (self.audience=='all' and self.member_ids):raise ValueError('REQUEST_INVALID')
        return self
class RollbackRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    client_request_id:UUID
    source_request_id:UUID
    expected_publication_revision:StrictInt=Field(ge=1,le=9223372036854775806)
    reason:StrictStr=Field(min_length=1,max_length=500)
    _text=field_validator('reason')(DeploymentRequest.text.__func__)

class DeploymentDecision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision:StrictInt=Field(ge=1,le=2)
    decision:Literal['approve','reject']
    comment:StrictStr=Field(min_length=1,max_length=500)
    quality_reviewed:StrictBool
    security_reviewed:StrictBool
    _text=field_validator('comment')(DeploymentRequest.text.__func__)
class RetireRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision:StrictInt=Field(ge=1,le=9223372036854775806)

class DeploymentRepository(ShareRepository):
    async def call(self,ctx,action,target,body,mode):
        import psycopg
        try:return await self.rpc(ctx,'asset_deployment',(ctx.session_id,ctx.tenant_id,action,target,Jsonb(body),mode))
        except psycopg.Error as error:
            if error.sqlstate=='D0429':raise AppError('DEPLOYMENT_QUEUE_FULL',409) from None
            raise
async def execute(request,action,target=None,body=None,query=False):
    ctx=await context(request,write=action in ('submit','decide','retire'));params=request.query_params
    if (set(params)-{'cursor'} if query else params) or any(len(params.getlist(k))!=1 for k in params):raise AppError('REQUEST_INVALID',422)
    await request.app.state.documents.read_window(ctx)
    return await DeploymentRepository(request.app.state.pool).call(ctx,action,target,body or {},request.app.state.settings.mode)
@router.post('')
async def submit(request:Request,body:DeploymentRequest):
    data=await execute(request,'submit',body=body.model_dump(mode='json'));return response(request,data,status_code=200 if data['replayed'] else 201)
@router.get('')
async def listing(request:Request,cursor:UUID|None=None):
    return response(request,await execute(request,'list',body={'cursor':str(cursor)} if cursor else {},query=True))
async def rollback_call(request,action,target=None,body=None,allowed=()):
    ctx=await context(request,write=action=='submit');params=request.query_params
    if set(params)-set(allowed) or any(len(params.getlist(k))!=1 for k in params):raise AppError('REQUEST_INVALID',422)
    await request.app.state.documents.read_window(ctx)
    return await DeploymentRepository(request.app.state.pool).rpc(ctx,'asset_rollback',(ctx.session_id,ctx.tenant_id,action,target,Jsonb(body or {}),request.app.state.settings.mode))
@router.post('/rollbacks')
async def rollback_submit(request:Request,body:RollbackRequest):
    data=await rollback_call(request,'submit',body=body.model_dump(mode='json'));return response(request,data,status_code=200 if data['replayed'] else 201)
@router.get('/publications/{asset_id}/history')
async def publication_history(request:Request,asset_id:UUID,cursor:int|None=None):
    if cursor is not None and not 1<=cursor<=9223372036854775806:raise AppError('REQUEST_INVALID',422)
    return response(request,await rollback_call(request,'history',asset_id,{'cursor':cursor} if cursor else {},('cursor',)))
@router.get('/publications/{asset_id}/compare')
async def publication_compare(request:Request,asset_id:UUID,left_revision:int,right_revision:int):
    if not 1<=left_revision<=9223372036854775806 or not 1<=right_revision<=9223372036854775806:raise AppError('REQUEST_INVALID',422)
    return response(request,await rollback_call(request,'compare',asset_id,{'left_revision':left_revision,'right_revision':right_revision},('left_revision','right_revision')))
@router.get('/publications/{asset_id}')
async def publication(request:Request,asset_id:UUID):return response(request,await execute(request,'publication',asset_id))
@router.post('/publications/{asset_id}/retire')
async def retire(request:Request,asset_id:UUID,body:RetireRequest):return response(request,await execute(request,'retire',asset_id,body.model_dump()))
@router.get('/{request_id}')
async def detail(request:Request,request_id:UUID):return response(request,await execute(request,'detail',request_id))
@router.post('/{request_id}/decision')
async def decision(request:Request,request_id:UUID,body:DeploymentDecision):return response(request,await execute(request,'decide',request_id,body.model_dump(mode='json')))
