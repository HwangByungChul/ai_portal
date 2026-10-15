from typing import Literal
from uuid import UUID, uuid4
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel, ConfigDict, StrictStr, StrictInt, Field, model_validator
from app.auth.crypto import window_digest
from app.assets.repository import AssetRepository
from app.errors import AppError, response
from app.tenants.routes import context

router = APIRouter(prefix='/api/v1/admin/assets')


class AssetConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: StrictStr = Field(min_length=1, max_length=80)
    description: StrictStr = Field(max_length=500)
    instructions: StrictStr = Field(min_length=1, max_length=2000)
    execution_kind: Literal['general', 'rules_rag']

    @model_validator(mode='after')
    def validate_text(self):
        for key in ('name', 'description', 'instructions'):
            value = getattr(self, key)
            if (key != 'description' and not value.strip()) or '\x00' in value:
                raise ValueError('TEXT_INVALID')
            try:
                value.encode('utf-8')
            except UnicodeError:
                raise ValueError('TEXT_INVALID') from None
        return self


class CreateAsset(BaseModel):
    model_config = ConfigDict(extra='forbid')
    client_request_id: UUID
    config: AssetConfig


class AppendVersion(CreateAsset):
    expected_revision: StrictInt = Field(ge=1, le=1000)


async def execute(request, action, asset_id=None, body=None, write=False):
    ctx = await context(request, write=write)
    allowed = {'cursor', 'limit'} if action == 'list' else set()
    if any(k not in allowed or len(request.query_params.getlist(k)) != 1 for k in request.query_params):
        raise AppError('REQUEST_INVALID', 422)
    settings = request.app.state.settings
    digest = None if write else window_digest(settings.login_hmac_secret.get_secret_value(), 'http_read', 'principal', str(ctx.user_id)+':'+str(ctx.tenant_id))
    return await AssetRepository(request.app.state.pool).call(ctx, action, asset_id, body or {},
        UUID(request.state.request_id) if write else None, digest)


@router.get('')
async def listing(request: Request, cursor: UUID | None = None, limit: int = Query(default=20, ge=1, le=50)):
    return response(request, await execute(request, 'list', body={'cursor': str(cursor) if cursor else None, 'limit': limit}))


@router.get('/{asset_id}')
async def detail(request: Request, asset_id: UUID):
    return response(request, await execute(request, 'detail', asset_id))


@router.post('')
async def create(request: Request, body: CreateAsset):
    data = await execute(request, 'create', uuid4(), body.model_dump(mode='json'), True)
    return response(request, data, status_code=200 if data['replayed'] else 201)


@router.post('/{asset_id}/versions')
async def append(request: Request, asset_id: UUID, body: AppendVersion):
    data = await execute(request, 'append', asset_id, body.model_dump(mode='json'), True)
    return response(request, data, status_code=200 if data['replayed'] else 201)
