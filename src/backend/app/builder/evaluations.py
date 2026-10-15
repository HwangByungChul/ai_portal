"""Private immutable case sets; deterministic checks are not semantic quality scores."""
from uuid import UUID
from typing import Literal
from fastapi import APIRouter,Request
from pydantic import BaseModel,ConfigDict,StrictStr,Field,field_validator,model_validator
from psycopg.types.json import Jsonb
from app.builder.schemas import ProfilePreview
from app.conversations.routes import DocumentRef,digest
from app.builder.trials import TrialRepository,valid
from app.execution.summary_routes import ensure_execution
from app.tenants.routes import context
from app.errors import AppError,response

router=APIRouter(prefix='/api/v1/admin/builder')
class Criteria(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_answer:Literal['answer','insufficient_evidence']
    required_terms:list[StrictStr]=Field(default_factory=list,max_length=10)
    forbidden_terms:list[StrictStr]=Field(default_factory=list,max_length=10)
    required_sources:list[DocumentRef]=Field(default_factory=list,max_length=5)
    @model_validator(mode='after')
    def bounds(self):
        for terms in (self.required_terms,self.forbidden_terms):
            if len(set(terms))!=len(terms) or any(not t.strip() or len(t)>200 or '\x00' in t for t in terms):raise ValueError('REQUEST_INVALID')
            for t in terms:t.encode('utf-8')
        if set(self.required_terms)&set(self.forbidden_terms):raise ValueError('REQUEST_INVALID')
        if len({(x.document_id,x.version_id) for x in self.required_sources})!=len(self.required_sources):raise ValueError('REQUEST_INVALID')
        return self
class CaseRequest(ProfilePreview):
    client_request_id:UUID
    name:StrictStr=Field(min_length=1,max_length=100)
    purpose:Literal['generate','search']='generate'
    criteria:Criteria
    @field_validator('name')
    @classmethod
    def name_valid(cls,v):
        if not v.strip() or '\x00' in v:raise ValueError('REQUEST_INVALID')
        v.encode('utf-8');return v
class CaseTrial(BaseModel):
    model_config=ConfigDict(extra='forbid')
    client_send_id:UUID
class EvaluateRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    run_id:UUID

@router.post('/assets/{asset_id}/versions/{version_id}/evaluation-cases')
async def save(request:Request,asset_id:UUID,version_id:UUID,body:CaseRequest):
    ctx=await context(request,write=True);valid(request)
    data=await TrialRepository(request.app.state.pool).rpc(ctx,'builder_case_save',(ctx.session_id,ctx.tenant_id,asset_id,version_id,body.client_request_id,Jsonb(body.model_dump(mode='json',exclude={'client_request_id'}))))
    return response(request,data,status_code=200 if data['replayed'] else 201)
@router.get('/assets/{asset_id}/versions/{version_id}/evaluation-cases')
async def listing(request:Request,asset_id:UUID,version_id:UUID,cursor:UUID|None=None):
    ctx=await context(request)
    if set(request.query_params)-{'cursor'}:raise AppError('REQUEST_INVALID',422)
    await request.app.state.documents.read_window(ctx)
    return response(request,await TrialRepository(request.app.state.pool).rpc(ctx,'builder_case_list',(ctx.session_id,ctx.tenant_id,asset_id,version_id,cursor)))
@router.get('/evaluation-cases/{case_id}')
async def read(request:Request,case_id:UUID):
    ctx=await context(request);valid(request);await request.app.state.documents.read_window(ctx)
    return response(request,await TrialRepository(request.app.state.pool).rpc(ctx,'builder_case_read',(ctx.session_id,ctx.tenant_id,case_id)))
@router.post('/evaluation-cases/{case_id}/trials')
async def trial(request:Request,case_id:UUID,body:CaseTrial):
    ctx=await context(request,write=True);valid(request);manager=ensure_execution(request);s=request.app.state.settings;repo=TrialRepository(request.app.state.pool)
    case=await repo.rpc(ctx,'builder_case_read',(ctx.session_id,ctx.tenant_id,case_id))
    data=await repo.admit(ctx,UUID(case['asset_id']),UUID(case['version_id']),{'client_send_id':str(body.client_send_id),'purpose':case['spec']['purpose'],'values':case['spec']['values']},s.budget_period,s.mode,digest(request,ctx,'run_admission'),UUID(request.state.request_id))
    if manager and not data['replayed'] and not data['is_terminal']:manager.notify(ctx,data['run_id'])
    return response(request,{k:data[k] for k in ('run_id','state','revision','replayed')},status_code=200 if data['replayed'] else 201)
@router.post('/evaluation-cases/{case_id}/checks')
async def evaluate(request:Request,case_id:UUID,body:EvaluateRequest):
    ctx=await context(request,write=True);valid(request);await request.app.state.documents.read_window(ctx)
    data=await TrialRepository(request.app.state.pool).rpc(ctx,'builder_case_evaluate',(ctx.session_id,ctx.tenant_id,case_id,body.run_id))
    return response(request,data,status_code=200 if data['replayed'] else 201)
