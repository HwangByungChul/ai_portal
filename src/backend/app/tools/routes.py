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
from app.tools.dynamic_repository import DynamicToolRepository
from app.tools.publication_gate import publication_gate

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

async def _current_descriptor(request,ctx,service,tool_id):
    try:
        return service.descriptor(tool_id)
    except AppError as error:
        if error.status != 404:
            raise
        data=await DynamicToolRepository(request.app.state.pool).approval_descriptor(ctx,tool_id,request.app.state.settings.mode)
        return data['descriptor']

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
    try:
        descriptor=service.descriptor(body.tool_id)
    except AppError as error:
        if error.status != 404:
            raise
        return response(request,await DynamicToolRepository(request.app.state.pool).submit_approval(
            ctx,tool_id=body.tool_id,client_request_id=body.client_request_id,audience=body.audience,
            member_ids=[str(member) for member in body.member_ids],expected_head_revision=body.expected_head_revision,
            mode=request.app.state.settings.mode))
    data=body.model_dump(mode='json');data.pop('tool_id');data['descriptor']=descriptor
    return response(request,await service.repository.approval(ctx,'submit',None,data))

@router.post('/admin/tool-approvals/{request_id}/decision')
async def decide_tool_approval(request:Request,request_id:UUID,body:ToolDecisionRequest):
    ctx=await context(request,write=True)
    if body.decision=='approve':
        detail=await ReviewRepository(control(request).repository,'tool',request.app.state.settings.mode,secret(request)).detail(ctx,request_id)
        descriptor=detail['request'].get('descriptor',{})
        if descriptor.get('approval_scope')=='registration_review_only':
            raise AppError('TOOL_DYNAMIC_REVIEW_ONLY',409)
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
    dynamic_items=await DynamicToolRepository(request.app.state.pool).list(ctx)
    for public in service.registry.list_public():
        descriptor=service.descriptor(public['tool_id']);head=heads.get(public['tool_id'])
        current=await ReviewRepository(service.repository,'tool',request.app.state.settings.mode).detail(ctx,UUID(head['request_id'])) if head else None
        items.append(public|{'descriptor':descriptor,'head_revision':head['revision'] if head else 0,'current_head':current['current_head'] if current else None,'execution_ready':bool(head and head['enabled'] and current and current['current_head']['descriptor']==descriptor and service.mode=='mock' and request.app.state.settings.execution_enabled)})
    for item in dynamic_items:
        try:
            state=await DynamicToolRepository(request.app.state.pool).approval_descriptor(ctx,item['tool_id'],request.app.state.settings.mode)
        except AppError:
            continue
        descriptor=state['descriptor'];head=heads.get(item['tool_id'])
        current=await ReviewRepository(service.repository,'tool',request.app.state.settings.mode).detail(ctx,UUID(head['request_id'])) if head else None
        items.append({'tool_id':item['tool_id'],'name':item['name'],'description':item['description'],
            'category':'dynamic','enabled':True,
            'dynamic':True,'risk_class':descriptor['risk_class'],'input_schema':item['input_schema'],
            'arg_schema':item['input_schema'],'timeout_seconds':0,
            'descriptor':descriptor,'head_revision':state['head_revision'],
            'current_head':current['current_head'] if current else None,'execution_ready':False})
    return response(request,{'items':items})

@router.get('/admin/tool-approvals/{request_id}')
async def tool_detail(request:Request,request_id:UUID):
    ctx=await context(request)
    if request.query_params:raise AppError('REQUEST_INVALID',422)
    data=await ReviewRepository(control(request).repository,'tool',request.app.state.settings.mode).detail(ctx,request_id)
    service=control(request)
    submitted_descriptor=data['request'].get('descriptor')
    descriptor=None
    try:
        descriptor=await _current_descriptor(request,ctx,service,data['request']['tool_id'])
        if descriptor!=data['request']['descriptor']:
            data['can_approve']=False;data['validation']['valid']=False
            data['validation']['checks'].append({'code':'DESCRIPTOR_CHANGED','status':'fail','message':'현재 도구 descriptor가 변경되었습니다.'})
        if descriptor.get('approval_scope')=='registration_review_only':
            data['can_approve']=False;data['validation']['valid']=False
            data['validation']['checks'].append({'code':'DYNAMIC_REGISTRATION_REVIEW_ONLY','status':'fail','message':'등록 검토 전용 정책입니다. 게시·실행 승인 gate가 연결되기 전 PADMIN 승인을 차단합니다.'})
    except AppError:
        data['can_approve']=False;data['validation']['valid']=False
        data['validation']['checks'].append({'code':'CONNECTOR_UNAVAILABLE','status':'unavailable','message':'현재 도구 연결을 사용할 수 없습니다.'})
    if (isinstance(submitted_descriptor,dict) and submitted_descriptor.get('approval_scope')=='registration_review_only') or (isinstance(descriptor,dict) and descriptor.get('approval_scope')=='registration_review_only'):
        data['publication_gate']=publication_gate(submitted_descriptor,descriptor)
    return response(request,data)


@router.get('/admin/tool-audit')
async def list_tool_audit(request: Request):
    ctx = await context(request)
    if ctx.role not in ('tenant_admin', 'platform_admin'):
        raise AppError('FORBIDDEN', 403)

    tool_id = request.query_params.get('tool_id')
    trace_id = request.query_params.get('trace_id')
    event_type = request.query_params.get('event_type')
    limit = min(int(request.query_params.get('limit', 50)), 200)

    audit_svc = getattr(request.app.state, 'audit_service', None)
    if not audit_svc:
        from app.tools.audit import AuditLedgerService
        audit_svc = AuditLedgerService(getattr(request.app.state, 'pool', None))
        request.app.state.audit_service = audit_svc

    events = audit_svc.get_events(
        str(ctx.tenant_id),
        tool_id=tool_id,
        trace_id=trace_id,
        event_type=event_type,
        limit=limit,
    )
    items = [
        {
            'event_id': e.event_id,
            'tenant_id': e.tenant_id,
            'tool_id': e.tool_id,
            'version_id': e.version_id,
            'revision_number': e.revision_number,
            'actor_id': e.actor_id,
            'trace_id': e.trace_id,
            'event_type': e.event_type,
            'argument_digest': e.argument_digest,
            'response_digest': e.response_digest,
            'duration_ms': e.duration_ms,
            'status': e.status,
            'error_code': e.error_code,
            'chain_hash': e.chain_hash,
            'created_at': e.created_at,
        }
        for e in events
    ]
    return response(request, {'items': items, 'count': len(items)})


@router.get('/admin/tool-health')
async def get_tool_health(request: Request):
    ctx = await context(request)
    if ctx.role not in ('tenant_admin', 'platform_admin'):
        raise AppError('FORBIDDEN', 403)

    dispatcher = getattr(request.app.state, 'dispatcher', None)
    tool_id = request.query_params.get('tool_id')
    circuit_state = 'closed'
    if dispatcher and tool_id:
        circuit_state = dispatcher.circuit_breaker.state(str(ctx.tenant_id), tool_id)

    return response(request, {
        'tenant_id': str(ctx.tenant_id),
        'tool_id': tool_id,
        'circuit_state': circuit_state,
        'status': 'healthy' if circuit_state == 'closed' else 'degraded',
    })

