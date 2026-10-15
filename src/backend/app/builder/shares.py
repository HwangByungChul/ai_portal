"""Consented minimum approval evidence; never changes private trial ownership."""
from uuid import UUID
import psycopg
from fastapi import APIRouter,Request
from pydantic import BaseModel,ConfigDict,StrictBool,StrictInt,Field,field_validator
from psycopg.types.json import Jsonb
from app.builder.trials import TrialRepository
from app.tenants.routes import context
from app.errors import AppError,response

router=APIRouter(prefix='/api/v1/admin/builder/evidence-shares')
class ShareRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    client_request_id:UUID
    run_id:UUID
    evaluation_id:UUID
    consent:StrictBool
    @field_validator('consent')
    @classmethod
    def explicit_consent(cls,v):
        if not v:raise ValueError('REQUEST_INVALID')
        return v
class WithdrawRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision:StrictInt=Field(ge=1,le=2)

class ShareRepository(TrialRepository):
    async def call(self,ctx,action,share_id,body,mode):
        try:
            return await self.rpc(ctx,'builder_evidence_share',(ctx.session_id,ctx.tenant_id,action,share_id,Jsonb(body),mode))
        except psycopg.Error as error:
            if error.sqlstate=='D0429':raise AppError('DEPLOYMENT_QUEUE_FULL',409) from None
            raise

async def call(request,action,share_id=None,body=None,query=False):
    ctx=await context(request,write=action in ('submit','withdraw'))
    params=request.query_params
    if (set(params)-{'cursor'} if query else params) or any(len(params.getlist(k))!=1 for k in params):raise AppError('REQUEST_INVALID',422)
    await request.app.state.documents.read_window(ctx)
    return await ShareRepository(request.app.state.pool).call(ctx,action,share_id,body or {},request.app.state.settings.mode)

@router.post('')
async def submit(request:Request,body:ShareRequest):
    data=await call(request,'submit',body=body.model_dump(mode='json'))
    return response(request,data,status_code=200 if data['replayed'] else 201)
@router.get('')
async def listing(request:Request,cursor:UUID|None=None):
    return response(request,await call(request,'list',body={'cursor':str(cursor)} if cursor else {},query=True))
@router.get('/{share_id}')
async def detail(request:Request,share_id:UUID):
    return response(request,await call(request,'detail',share_id))
@router.post('/{share_id}/withdraw')
async def withdraw(request:Request,share_id:UUID,body:WithdrawRequest):
    return response(request,await call(request,'withdraw',share_id,body.model_dump()))
