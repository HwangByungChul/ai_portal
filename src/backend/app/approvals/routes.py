from typing import Literal
from uuid import UUID, uuid4
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel, ConfigDict, StrictStr, StrictInt, Field, model_validator
from app.auth.crypto import window_digest
from app.errors import AppError, response
from app.tenants.routes import context
from app.approvals.repository import ApprovalRepository

router = APIRouter(prefix='/api/v1/admin/agent-deployments')


class Proposal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    client_request_id: UUID
    agent_key: Literal['general', 'rules_rag']
    expected_revision: StrictInt = Field(ge=1, le=9223372036854775807)
    name: StrictStr = Field(min_length=1, max_length=80)
    description: StrictStr = Field(max_length=500)
    instructions: StrictStr = Field(min_length=1, max_length=2000)
    reason: StrictStr = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def validate_text(self):
        for key in ('name', 'description', 'instructions', 'reason'):
            value = getattr(self, key)
            if key != 'description' and not value.strip():
                raise ValueError('TEXT_REQUIRED')
            try:
                value.encode('utf-8')
            except UnicodeError:
                raise ValueError('TEXT_INVALID') from None
            if '\x00' in value:
                raise ValueError('TEXT_INVALID')
        return self


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decision: Literal['approve', 'reject']
    expected_revision: StrictInt = Field(ge=1, le=9223372036854775807)
    comment: StrictStr = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def validate_text(self):
        if not self.comment.strip() or '\x00' in self.comment:
            raise ValueError('TEXT_REQUIRED')
        try:
            self.comment.encode('utf-8')
        except UnicodeError:
            raise ValueError('TEXT_INVALID') from None
        return self


async def execute(request, action, request_id=None, body=None, write=False):
    ctx = await context(request, write=write)
    allowed = {'status', 'cursor', 'limit'} if action == 'list' else set()
    if any(k not in allowed or len(request.query_params.getlist(k)) != 1 for k in request.query_params):
        raise AppError('REQUEST_INVALID', 422)
    settings = request.app.state.settings
    digest = None if write else window_digest(settings.login_hmac_secret.get_secret_value(), 'http_read', 'principal', str(ctx.user_id)+':'+str(ctx.tenant_id))
    return await ApprovalRepository(request.app.state.pool).call(
        ctx, action, request_id, body or {}, settings.budget_period, settings.mode,
        UUID(request.state.request_id) if write else None, digest)


@router.post('')
async def submit(request: Request, body: Proposal):
    data = await execute(request, 'submit', uuid4(), body.model_dump(mode='json'), True)
    return response(request, data, status_code=200 if data['replayed'] else 201)


@router.get('')
async def listing(request: Request, status: Literal['pending', 'approved', 'rejected'] | None = None,
                  cursor: UUID | None = None, limit: int = Query(default=20, ge=1, le=50)):
    return response(request, await execute(request, 'list', body={'status': status, 'cursor': str(cursor) if cursor else None, 'limit': limit}))


@router.get('/{request_id}')
async def detail(request: Request, request_id: UUID):
    return response(request, await execute(request, 'detail', request_id))


@router.post('/{request_id}/decision')
async def decide(request: Request, request_id: UUID, body: Decision):
    return response(request, await execute(request, 'decide', request_id, body.model_dump(), True))
