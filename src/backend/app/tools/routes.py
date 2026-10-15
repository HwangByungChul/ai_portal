"""Authenticated Tool catalog, owner receipts and separate administrative approval."""
from typing import Any,Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,StrictInt,StrictStr
from fastapi import APIRouter,Request
from app.tools.registry import GLOBAL_TOOL_REGISTRY
from app.approval_reviews.models import ReviewComment
from app.approval_reviews.repository import ReviewRepository,query_page,secret
from app.errors import AppError,response
from app.tenants.routes import context

router=APIRouter(prefix='/api/v1')

class ToolInvokeRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    arguments:dict[str,Any]=Field(default_factory=dict)
    client_request_id:UUID

class ToolApprovalRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    client_request_id:UUID
    tool_id:StrictStr
    audience:Literal['all','restricted']='restricted'
    member_ids:list[UUID]=Field(default_factory=list,max_length=200)
    expected_head_revision:StrictInt=Field(ge=0,le=9223372036854775806)

class ToolDecisionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    comment:ReviewComment
    decision:Literal['approve','reject']
    expected_revision:StrictInt=Field(ge=1,le=9223372036854775806)

class ToolRevokeRequest(BaseModel):
    comment:ReviewComment
    model_config=ConfigDict(extra='forbid')
    expected_revision:StrictInt=Field(ge=1,le=9223372036854775806)

def control(request):
    service=getattr(request.app.state,'tool_control',None)
    if service is None:raise AppError('EXECUTION_NOT_READY',409)
    return service

@router.get('/tools')
async def list_tools(request:Request):
    ctx=await context(request)
    service=getattr(request.app.state,'tool_control',None)
    tools=await service.ready(ctx) if service else [t|{'execution_ready':False} for t in GLOBAL_TOOL_REGISTRY.list_public()]
    if not request.app.state.settings.execution_enabled:
        tools=[t|{'execution_ready':False} for t in tools]
    return response(request,{'items':tools})

@router.post('/tools/{tool_id}/invoke')
async def invoke_tool(request:Request,tool_id:str,body:ToolInvokeRequest):
    ctx=await context(request,write=True)
    executor=getattr(request.app.state,'tool_execution',None)
    if not request.app.state.settings.execution_enabled or executor is None:raise AppError('EXECUTION_NOT_READY',409)
    result=await executor.invoke(ctx,tool_id,body.arguments,body.client_request_id)
    return response(request,result)

@router.get('/tools/{tool_id}/receipts/{client_request_id}')
async def read_tool_receipt(request:Request,tool_id:str,client_request_id:UUID):
    ctx=await context(request)
    return response(request,await control(request).read(ctx,tool_id,client_request_id))

@router.get('/admin/tool-approvals')
async def list_tool_approvals(request:Request):
    ctx=await context(request)
    return response(request,await ReviewRepository(control(request).repository,'tool',request.app.state.settings.mode,secret(request)).page(ctx,**query_page(request)))

@router.post('/admin/tool-approvals')
async def submit_tool_approval(request:Request,body:ToolApprovalRequest):
    ctx=await context(request,write=True);service=control(request)
    descriptor=service.descriptor(body.tool_id)
    data=body.model_dump(mode='json');data.pop('tool_id');data['descriptor']=descriptor
    return response(request,await service.repository.approval(ctx,'submit',None,data))

@router.post('/admin/tool-approvals/{request_id}/decision')
async def decide_tool_approval(request:Request,request_id:UUID,body:ToolDecisionRequest):
    ctx=await context(request,write=True)
    return response(request,await control(request).repository.approval(ctx,body.decision,request_id,{'expected_revision':body.expected_revision,'comment':body.comment},mode=request.app.state.settings.mode))

@router.post('/admin/tools/{tool_id}/revoke')
async def revoke_tool(request:Request,tool_id:str,body:ToolRevokeRequest):
    ctx=await context(request,write=True)
    return response(request,await control(request).repository.approval(ctx,'revoke',None,{'tool_id':tool_id,'expected_revision':body.expected_revision,'comment':body.comment}))

@router.get('/admin/tool-approvals/submission-support')
async def tool_submission_support(request:Request):
    ctx=await context(request);service=control(request)
    data=await ReviewRepository(service.repository,'tool',request.app.state.settings.mode).read(ctx,body={'action':'support'})
    heads={h['tool_id']:h for h in data['heads']}
    items=[]
    for public in service.registry.list_public():
        descriptor=service.descriptor(public['tool_id']);head=heads.get(public['tool_id'])
        current=await ReviewRepository(service.repository,'tool',request.app.state.settings.mode).detail(ctx,UUID(head['request_id'])) if head else None
        items.append(public|{'descriptor':descriptor,'head_revision':head['revision'] if head else 0,'current_head':current['current_head'] if current else None,'execution_ready':bool(head and head['enabled'] and current and current['current_head']['descriptor']==descriptor and service.mode=='mock' and request.app.state.settings.execution_enabled)})
    return response(request,{'items':items})

@router.get('/admin/tool-approvals/{request_id}')
async def tool_detail(request:Request,request_id:UUID):
    ctx=await context(request)
    if request.query_params:raise AppError('REQUEST_INVALID',422)
    data=await ReviewRepository(control(request).repository,'tool',request.app.state.settings.mode).detail(ctx,request_id)
    service=control(request)
    try:
        descriptor=service.descriptor(data['request']['tool_id'])
        if descriptor!=data['request']['descriptor']:
            data['can_approve']=False;data['validation']['valid']=False
            data['validation']['checks'].append({'code':'DESCRIPTOR_CHANGED','status':'fail','message':'현재 도구 descriptor가 변경되었습니다.'})
    except AppError:
        data['can_approve']=False;data['validation']['valid']=False
        data['validation']['checks'].append({'code':'CONNECTOR_UNAVAILABLE','status':'unavailable','message':'현재 도구 연결을 사용할 수 없습니다.'})
    return response(request,data)
