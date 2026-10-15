from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel, ConfigDict, StrictInt, StrictBool, Field
from app.auth.crypto import window_digest
from app.catalog.repository import CatalogRepository
from app.errors import AppError, response
from app.tenants.routes import context
from app.operations.routes import apply_agent_readiness

router = APIRouter(prefix='/api/v1')

class FavoriteWrite(BaseModel):
    model_config = ConfigDict(extra='forbid')
    client_request_id: UUID
    expected_revision: StrictInt = Field(ge=0,le=9223372036854775806)
    active: StrictBool

class AccessWrite(BaseModel):
    model_config = ConfigDict(extra='forbid')
    client_request_id: UUID
    expected_revision: StrictInt = Field(ge=0,le=9223372036854775806)
    mode: Literal['all','restricted']
    member_ids: list[UUID] = Field(max_length=200)

async def execute(request,action,asset_id=None,agent=None,body=None):
    write=action in ('favorite','access_set')
    ctx=await context(request,write=write)
    allowed={'q','category','mine','limit','cursor'} if action=='list' else {'cursor','limit'} if action=='members' else set()
    if any(k not in allowed or len(request.query_params.getlist(k))!=1 for k in request.query_params): raise AppError('REQUEST_INVALID',422)
    settings=request.app.state.settings
    digest=window_digest(settings.login_hmac_secret.get_secret_value(),'http_read','principal',str(ctx.user_id)+':'+str(ctx.tenant_id))
    data=await CatalogRepository(request.app.state.pool).call(ctx,action,asset_id,agent,body,settings.budget_period,settings.mode,UUID(request.state.request_id) if write else None,digest)
    if action=='list': await apply_agent_readiness(request,ctx,data)
    elif action=='detail': await apply_agent_readiness(request,ctx,{'items':[data]})
    return response(request,data)

@router.get('/catalog/assets')
async def listing(request:Request,q:str=Query(default='',max_length=80),category:Literal['all','general','knowledge']='all',mine:Literal['true','false']='false',limit:int=Query(default=20,ge=1,le=50),cursor:UUID|None=None):
    try: q.encode('utf-8')
    except UnicodeError: raise AppError('REQUEST_INVALID',422) from None
    if '\x00' in q: raise AppError('REQUEST_INVALID',422)
    return await execute(request,'list',body={'q':q,'category':category,'mine':mine=='true','limit':limit,'cursor':str(cursor) if cursor else None})

@router.get('/catalog/assets/{asset_id}')
async def detail(request:Request,asset_id:UUID): return await execute(request,'detail',asset_id)

@router.put('/catalog/assets/{asset_id}/favorite')
async def favorite(request:Request,asset_id:UUID,body:FavoriteWrite): return await execute(request,'favorite',asset_id,body=body.model_dump(mode='json'))

@router.get('/admin/agent-access/{agent_key}')
async def access_get(request:Request,agent_key:Literal['general','rules_rag']): return await execute(request,'access_get',agent=agent_key,body={'agent_key':agent_key})

@router.put('/admin/agent-access/{agent_key}')
async def access_set(request:Request,agent_key:Literal['general','rules_rag'],body:AccessWrite): return await execute(request,'access_set',agent=agent_key,body=body.model_dump(mode='json'))


@router.get('/admin/agent-access/{agent_key}/members')
async def eligible_members(request:Request,agent_key:Literal['general','rules_rag'],limit:int=Query(default=50,ge=1,le=50),cursor:UUID|None=None):
    return await execute(request,'members',agent=agent_key,body={'agent_key':agent_key,'limit':limit,'cursor':str(cursor) if cursor else None})
