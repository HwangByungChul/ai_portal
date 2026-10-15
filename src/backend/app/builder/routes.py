"""Saved draft composition only: no provider, run, metering or publication."""
import hashlib
import json
from uuid import UUID
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr, Field
from app.assets.repository import AssetRepository
from app.auth.crypto import window_digest
from app.conversations.routes import DocumentRef
from app.documents.search import SearchRepository
from app.errors import AppError, response
from app.tenants.routes import context

router = APIRouter(prefix='/api/v1/admin/builder')


class Preview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: StrictInt = Field(ge=1, le=1000)
    values: dict[str, StrictStr] = Field(default_factory=dict, max_length=20)
    document_refs: list[DocumentRef] = Field(default_factory=list, max_length=5)


@router.post('/assets/{asset_id}/preview')
async def preview(request: Request, asset_id: UUID, body: Preview):
    ctx = await context(request, write=True)
    if request.query_params:
        raise AppError('REQUEST_INVALID', 422)
    settings = request.app.state.settings
    digest = window_digest(settings.login_hmac_secret.get_secret_value(), 'http_read', 'principal', str(ctx.user_id)+':'+str(ctx.tenant_id))
    detail = await AssetRepository(request.app.state.pool).call(ctx, 'detail', asset_id, {}, digest=digest)
    if detail['state'] != 'draft':
        raise AppError('ASSET_LEGACY_READ_ONLY', 409)
    if detail['latest_revision'] != body.expected_revision:
        raise AppError('REVISION_CONFLICT', 409)
    from app.builder.templates import compile_template
    names, instructions = compile_template(detail['config']['instructions'], body.values)
    if body.document_refs and detail['config']['execution_kind'] != 'rules_rag':
        raise AppError('REQUEST_INVALID', 422)
    sources = ()
    if body.document_refs:
        sources = await SearchRepository(request.app.state.documents).allowed(
            ctx, [ref.model_dump(mode='json') for ref in body.document_refs], settings.mode)
    sealed = {'asset_id': str(asset_id), 'version_id': str(detail['version_id']),
              'revision': detail['latest_revision'], 'config_hash': detail['config_hash'],
              'instructions': instructions, 'sources': list(sources)}
    fingerprint = hashlib.sha256(json.dumps(sealed, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return response(request, {**sealed, 'variables': names, 'composition_hash': fingerprint,
                              'kind': 'composition_preview', 'provider_called': False})
