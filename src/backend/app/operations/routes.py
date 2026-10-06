from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter,Request,Query
from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt,StrictStr,StringConstraints,model_validator
from app.auth.guards import check_transport,check_write,check_csrf,cookie_token
from app.auth.crypto import window_digest
from app.errors import AppError,response
from app.operations.repository import OperationsRepository
from app.tenants.routes import context as tenant_context
from app.types import AuthContext

router=APIRouter(prefix='/api/v1')
Revision=Annotated[StrictInt,Field(ge=1,le=9223372036854775807)]
Money=Annotated[StrictStr,StringConstraints(pattern=r'^(0|[1-9][0-9]{0,8})(\.[0-9]{1,2})?$')]


class AgentSettingsRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name: StrictStr|None=Field(default=None,max_length=80)
    description: StrictStr|None=Field(default=None,max_length=500)
    instructions: StrictStr|None=Field(default=None,max_length=2000)
    expected_revision: Revision

    @model_validator(mode='after')
    def validate_changes(self):
        fields=self.model_fields_set-{'expected_revision'}
        if not fields:raise ValueError('SETTING_REQUIRED')
        for key in fields:
            value=getattr(self,key)
            if value is None or (key!='description' and not value.strip()):raise ValueError('SETTING_REJECTED')
            try:value.encode('utf-8')
            except UnicodeError:raise ValueError('SETTING_REJECTED') from None
        return self


class AvailabilityRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    enabled: StrictBool
    expected_revision: Revision


class LocalBudgetRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    local_cap_krw: Money
    expected_revision: Revision

    @model_validator(mode='after')
    def validate_amount(self):
        if Decimal(self.local_cap_krw)>25000:raise ValueError('AMOUNT_REJECTED')
        return self


class AllocationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    allocated_cap_krw: Money
    expected_revision: Revision

    @model_validator(mode='after')
    def validate_amount(self):
        if Decimal(self.allocated_cap_krw)>25000:raise ValueError('AMOUNT_REJECTED')
        return self


async def global_context(request,write=False):
    settings=request.app.state.settings
    if write:check_write(request,settings,json_body=True)
    else:check_transport(request,settings)
    session=await request.app.state.auth.validate(cookie_token(request,settings))
    if write:check_csrf(request,session.csrf_secret)
    # Effective authority is freshly checked by the fixed DB function; role is never a header claim.
    return AuthContext(session.session_id,session.user_id,None,'USER',session.csrf_secret)


def validate_query(request,allowed):
    if any(k not in allowed or len(request.query_params.getlist(k))!=1 for k in request.query_params):
        raise AppError('REQUEST_INVALID',422)


async def read(request,kind,*,agent=None,period=None,cursor=None,limit=20):
    global_scope=kind=='platform_summary'
    ctx=await global_context(request) if global_scope else await tenant_context(request)
    validate_query(request,{'period','cursor','limit'} if kind=='usage_admin' else {'period'} if kind in ('usage_me','platform_summary') else set())
    settings=request.app.state.settings;period=period or settings.budget_period
    if period.day!=1:raise AppError('REQUEST_INVALID',422)
    digest=window_digest(settings.login_hmac_secret.get_secret_value(),'http_read','principal',str(ctx.user_id)+':'+(str(ctx.tenant_id) if ctx.tenant_id else 'platform'))
    data=await OperationsRepository(request.app.state.pool).read(ctx,kind,period,settings.mode,digest,agent,cursor,limit)
    manager=getattr(request.app.state,'execution',None)
    if kind=='agents' and manager is not None:
        from app.ai.repository import ExecutionError
        try:readiness=await manager.repository.readiness(ctx,settings.mode)
        except ExecutionError:raise AppError('STORAGE_UNAVAILABLE',503) from None
        if manager.gateway.stop_latch:readiness={'available':False,'safe_block_reason':'PROJECT_STOPPED'}
        for item in data['items']:
            if item['agent_key']=='general':item.update(readiness)
            elif item['agent_key']=='rules_rag' and getattr(manager,'rag',None) is not None:
                try:rag_ready=await manager.repository._rpc(manager.repository.web_pool,'rag_readiness',(ctx.session_id,ctx.tenant_id,settings.budget_period,settings.mode),ctx)
                except ExecutionError:raise AppError('STORAGE_UNAVAILABLE',503) from None
                if manager.gateway.stop_latch or manager.rag.query.stop_latch:rag_ready={'available':False,'safe_block_reason':'PROJECT_STOPPED'}
                item.update(rag_ready)
    return response(request,data)


async def mutate(request,kind,body,*,agent=None,target=None):
    ctx=await global_context(request,True) if kind=='global_availability' else await tenant_context(request,write=True)
    validate_query(request,set())
    if target is not None and target!=ctx.tenant_id:raise AppError('REQUEST_INVALID',422)
    settings=request.app.state.settings
    data=await OperationsRepository(request.app.state.pool).mutate(ctx,kind,settings.budget_period,settings.mode,
        body.model_dump(exclude_unset=True,exclude={'expected_revision'}),body.expected_revision,UUID(request.state.request_id),agent)
    return response(request,data)


@router.get('/agents')
async def agents(request:Request):return await read(request,'agents')

@router.get('/admin/agents/{agent_key}')
async def agent(request:Request,agent_key:str):return await read(request,'agent_admin',agent=agent_key)

@router.patch('/admin/agents/{agent_key}')
async def settings(request:Request,agent_key:str,body:AgentSettingsRequest):return await mutate(request,'agent_settings',body,agent=agent_key)

@router.put('/admin/agents/{agent_key}/availability')
async def availability(request:Request,agent_key:str,body:AvailabilityRequest):return await mutate(request,'agent_availability',body,agent=agent_key)

@router.get('/usage/me')
async def own_usage(request:Request,period:date|None=None):return await read(request,'usage_me',period=period)

@router.get('/admin/usage')
async def admin_usage(request:Request,period:date|None=None,cursor:UUID|None=None,limit:int=Query(default=20,ge=1,le=50)):
    return await read(request,'usage_admin',period=period,cursor=cursor,limit=limit)

@router.get('/admin/budget')
async def budget(request:Request):return await read(request,'budget_admin')

@router.put('/admin/budget')
async def local_budget(request:Request,body:LocalBudgetRequest):return await mutate(request,'local_budget',body)

@router.get('/platform/summary')
async def platform_summary(request:Request,period:date|None=None):return await read(request,'platform_summary',period=period)

@router.put('/platform/availability')
async def platform_availability(request:Request,body:AvailabilityRequest):return await mutate(request,'global_availability',body)

@router.put('/platform/tenant-budgets/{tenant_id}')
async def allocation(request:Request,tenant_id:UUID,body:AllocationRequest):return await mutate(request,'allocated_budget',body,target=tenant_id)
