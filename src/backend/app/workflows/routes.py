"""Approval-gated immutable Workflow version APIs."""
from typing import Any,Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,StrictInt,StrictStr
from fastapi import APIRouter,Request
from app.workflows.models import WorkflowDefinition
from app.approval_reviews.models import ReviewComment
from app.approval_reviews.repository import ReviewRepository,query_page,secret
from app.use_cases.meeting import meeting_contract
from app.workflows.approved_models import ApprovedWorkflow
from app.workflows.repository import WorkflowRepository
from app.errors import AppError,response
from app.tenants.routes import context

router=APIRouter(prefix='/api/v1/workflows')
admin=APIRouter(prefix='/api/v1/admin/workflow-approvals')

class SubmitWorkflow(BaseModel):
 model_config=ConfigDict(extra='forbid')
 definition:ApprovedWorkflow
 client_request_id:UUID
 audience:Literal['all','restricted']='restricted'
 member_ids:list[UUID]=Field(default_factory=list,max_length=200)
 expected_head_revision:StrictInt=Field(ge=0,le=9223372036854775806)
 use_case_id:Literal['AGENT_03']|None=None
 expected_use_case_revision:StrictInt=Field(default=0,ge=0,le=9223372036854775806)

class Decision(BaseModel):
 model_config=ConfigDict(extra='forbid')
 comment:ReviewComment
 decision:Literal['approve','reject']
 expected_revision:StrictInt=Field(ge=1,le=9223372036854775806)

class Revoke(BaseModel):
 comment:ReviewComment
 model_config=ConfigDict(extra='forbid')
 expected_revision:StrictInt=Field(ge=1,le=9223372036854775806)

class RunApprovedWorkflow(BaseModel):
 model_config=ConfigDict(extra='forbid')
 version_id:UUID
 client_request_id:UUID
 inputs:dict[str,StrictStr]=Field(default_factory=dict,max_length=20)

class LegacyRunWorkflow(BaseModel):
 model_config=ConfigDict(extra='forbid')
 workflow:WorkflowDefinition
 inputs:dict[str,Any]=Field(default_factory=dict)

def repository(request):
 value=getattr(request.app.state,'workflow_repository',None)
 if value is None:raise AppError('EXECUTION_NOT_READY',409)
 return value

@router.get('/catalog')
async def catalog(request:Request):
 ctx=await context(request)
 result=await repository(request).approval(ctx,'catalog',None,{},request.app.state.settings.mode)
 ready=bool(getattr(request.app.state,'workflow_execution',None)) and request.app.state.settings.execution_enabled
 return response(request,{'items':[item|{'execution_ready':ready} for item in result['items']]})

@router.post('/validate')
async def validate_workflow(request:Request,body:WorkflowDefinition):
 ctx=await context(request,write=True)
 if ctx.effective_role not in ('TADMIN','PADMIN'):raise AppError('MANAGEMENT_DENIED',403)
 if len(body.nodes)>20 or len(body.edges)>30:raise AppError('REQUEST_INVALID',422)
 return response(request,{'valid':True,'workflow_id':body.workflow_id,'node_count':len(body.nodes),'execution_order':body.get_execution_order()})

@router.post('/run')
async def run_workflow(request:Request,body:RunApprovedWorkflow|LegacyRunWorkflow):
 ctx=await context(request,write=True)
 if request.query_params:raise AppError('REQUEST_INVALID',422)
 service=getattr(request.app.state,'workflow_execution',None)
 if isinstance(body,LegacyRunWorkflow) or not request.app.state.settings.execution_enabled or service is None:raise AppError('EXECUTION_NOT_READY',409)
 data=await service.admit(ctx,body.version_id,body.client_request_id,body.inputs,UUID(request.state.request_id))
 return response(request,data,status_code=200 if data['replayed'] else 202)

@router.get('/runs/{run_id}')
async def read_workflow(request:Request,run_id:UUID):
 ctx=await context(request)
 if request.query_params:raise AppError('REQUEST_INVALID',422)
 await request.app.state.documents.read_window(ctx)
 service=getattr(request.app.state,'workflow_control',None)
 if service is None:raise AppError('EXECUTION_NOT_READY',409)
 return response(request,await service.read(ctx,run_id))

class CancelWorkflow(BaseModel):
 model_config=ConfigDict(extra='forbid')
 expected_revision:StrictInt=Field(ge=1,le=9223372036854775806)

@router.post('/runs/{run_id}/cancel')
async def cancel_workflow(request:Request,run_id:UUID,body:CancelWorkflow):
 ctx=await context(request,write=True)
 if request.query_params:raise AppError('REQUEST_INVALID',422)
 service=getattr(request.app.state,'workflow_control',None)
 if service is None:raise AppError('EXECUTION_NOT_READY',409)
 return response(request,await service.cancel(ctx,run_id,body.expected_revision,UUID(request.state.request_id)))

@admin.get('')
async def list_approvals(request:Request):
 ctx=await context(request)
 return response(request,await ReviewRepository(repository(request),'workflow',request.app.state.settings.mode,secret(request)).page(ctx,**query_page(request)))

@admin.post('')
async def submit_approval(request:Request,body:SubmitWorkflow):
 ctx=await context(request,write=True);definition=body.definition.model_dump(mode='json')
 digest=WorkflowRepository.digest(definition)
 payload={'workflow_id':str(body.definition.workflow_id),'client_request_id':str(body.client_request_id),'definition':definition,'version_digest':digest,'audience':body.audience,'member_ids':[str(x) for x in body.member_ids],'expected_head_revision':body.expected_head_revision}
 if body.use_case_id is not None:payload.update({'use_case_id':body.use_case_id,'expected_use_case_revision':body.expected_use_case_revision})
 result=await repository(request).approval(ctx,'submit',None,payload,request.app.state.settings.mode,UUID(request.state.request_id))
 return response(request,result)

@admin.post('/{version_id}/decision')
async def decide(request:Request,version_id:UUID,body:Decision):
 ctx=await context(request,write=True)
 return response(request,await repository(request).approval(ctx,body.decision,version_id,{'expected_revision':body.expected_revision,'comment':body.comment},request.app.state.settings.mode,UUID(request.state.request_id)))

@admin.post('/{workflow_id}/revoke')
async def revoke(request:Request,workflow_id:UUID,body:Revoke):
 ctx=await context(request,write=True)
 return response(request,await repository(request).approval(ctx,'revoke',None,{'workflow_id':str(workflow_id),'expected_revision':body.expected_revision,'comment':body.comment},request.app.state.settings.mode,UUID(request.state.request_id)))

@router.post('/approved/validate')
async def validate_approved(request:Request,body:ApprovedWorkflow):
 ctx=await context(request,write=True)
 if ctx.effective_role not in ('TADMIN','PADMIN'):raise AppError('MANAGEMENT_DENIED',403)
 return response(request,{'valid':True,'workflow_id':str(body.workflow_id),'node_count':len(body.nodes),'execution_order':body.order()})

@admin.get('/submission-support')
async def workflow_submission_support(request:Request):
 ctx=await context(request)
 data=await ReviewRepository(repository(request),'workflow',request.app.state.settings.mode).read(ctx,body={'action':'support'})
 return response(request,{'workflow_heads':data['heads'],'use_case_heads':data['use_case_heads'],'meeting_contract':meeting_contract(),'published_assets_endpoint':'/api/v1/published-agents'})

@admin.get('/{version_id}')
async def workflow_detail(request:Request,version_id:UUID):
 ctx=await context(request)
 if request.query_params:raise AppError('REQUEST_INVALID',422)
 return response(request,await ReviewRepository(repository(request),'workflow',request.app.state.settings.mode).detail(ctx,version_id))
