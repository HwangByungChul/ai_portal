from dataclasses import asdict
from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from app.auth.crypto import window_digest
from app.auth.guards import check_csrf,check_transport,check_write,cookie_token
from app.errors import AppError,response
from app.tenants.repository import TenantRepository

router=APIRouter(prefix='/api/v1')


class ActiveRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    active: StrictBool
    expected_revision: StrictInt=Field(ge=1,le=9223372036854775807)


class RoleRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    role: Literal['USER','TADMIN']
    expected_revision: StrictInt=Field(ge=1,le=9223372036854775807)


async def context(request,*,write=False):
    settings,auth=request.app.state.settings,request.app.state.auth
    if write: check_write(request,settings,json_body=True)
    else: check_transport(request,settings)
    token=cookie_token(request,settings)
    session=await auth.validate(token)
    if write: check_csrf(request,session.csrf_secret)
    values=request.headers.getlist('x-tenant-id')
    if len(values)!=1:
        raise AppError('REQUEST_INVALID',422)
    try: tenant=UUID(values[0])
    except (ValueError,AttributeError): raise AppError('REQUEST_INVALID',422) from None
    ctx=await auth.resolve_tenant(token,tenant)
    request.state.tenant_id=str(tenant)
    return ctx


def public_row(row):
    return {k:str(v) if isinstance(v,UUID) else v for k,v in asdict(row).items()}


@router.get('/me/tenants')
async def own_tenants(request: Request):
    settings,auth=request.app.state.settings,request.app.state.auth
    check_transport(request,settings)
    session=await auth.validate(cookie_token(request,settings))
    rows=await TenantRepository(request.app.state.pool).own_tenants(session)
    return response(request,{'items':[public_row(row) for row in rows]})


@router.get('/admin/memberships')
async def memberships(request: Request,cursor: UUID|None=None,limit: int=Query(default=20,ge=1,le=50)):
    ctx=await context(request)
    if any(len(request.query_params.getlist(k))>1 for k in ('cursor','limit')):
        raise AppError('REQUEST_INVALID',422)
    secret=request.app.state.settings.login_hmac_secret.get_secret_value()
    digest=window_digest(secret,'http_read','principal',str(ctx.user_id)+':'+str(ctx.tenant_id))
    page=await TenantRepository(request.app.state.pool).members(ctx,cursor,limit,digest)
    return response(request,{'items':[public_row(row) for row in page.items],
                             'next_cursor':str(page.next_cursor) if page.next_cursor else None})


@router.patch('/admin/memberships/{user_id}')
async def change_active(request: Request,user_id: UUID,body: ActiveRequest):
    ctx=await context(request,write=True)
    row=await TenantRepository(request.app.state.pool).mutate(ctx,user_id,'active',body.active,None,
        body.expected_revision,UUID(request.state.request_id))
    return response(request,public_row(row))


@router.put('/admin/memberships/{user_id}/role')
async def change_role(request: Request,user_id: UUID,body: RoleRequest):
    ctx=await context(request,write=True)
    row=await TenantRepository(request.app.state.pool).mutate(ctx,user_id,'role',None,body.role,
        body.expected_revision,UUID(request.state.request_id))
    return response(request,public_row(row))
