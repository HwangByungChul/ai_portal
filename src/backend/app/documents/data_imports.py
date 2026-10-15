"""DP-17 Data Scope & Import Approval Domain Module."""
from uuid import UUID
from typing import Literal
import psycopg
from pydantic import BaseModel, ConfigDict, Field, StrictStr, StrictInt
from fastapi import APIRouter, Request
from app.tenants.routes import context
from app.db import tenant_transaction
from app.errors import AppError, response

router = APIRouter(prefix='/api/v1')

class CreateDataImport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    client_request_id: UUID
    document_id: UUID
    version_id: UUID
    classification: Literal['internal', 'confidential', 'restricted'] = 'internal'
    target_scope: Literal['org', 'department', 'team'] = 'org'
    reason: StrictStr = Field(min_length=1, max_length=500)

class DecideDataImport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decision: Literal['approved', 'rejected']
    comment: StrictStr = Field(default='', max_length=500)
    expected_revision: StrictInt = Field(ge=1, le=10000)

class DataImportRepository:
    def __init__(self, pool):
        self.pool = pool

    async def rpc(self, ctx, name: str, args: tuple):
        try:
            async with tenant_transaction(self.pool, ctx) as conn:
                query = f"SELECT security.{name}({','.join(['%s']*len(args))}) AS data"
                row = await (await conn.execute(query, args)).fetchone()
                return row['data']
        except (psycopg.Error, ValueError) as error:
            sqlstate = getattr(error, 'sqlstate', None)
            if sqlstate == 'A0403':
                # Check for SOD error
                msg = str(error)
                if 'SELF_APPROVAL_FORBIDDEN' in msg:
                    raise AppError('SELF_APPROVAL_FORBIDDEN', 403) from None
                raise AppError('PERMISSION_DENIED', 403) from None
            if sqlstate == 'A0404':
                raise AppError('RESOURCE_NOT_FOUND', 404) from None
            if sqlstate == 'A0409':
                raise AppError('REVISION_CONFLICT', 409) from None
            if sqlstate == 'A0422':
                raise AppError('REQUEST_INVALID', 422) from None
            raise AppError('STORAGE_UNAVAILABLE', 500) from None

    async def request_import(self, ctx, body: CreateDataImport, trace_id: UUID):
        return await self.rpc(
            ctx,
            'data_import_request',
            (
                ctx.session_id,
                trace_id,
                ctx.tenant_id,
                body.document_id,
                body.version_id,
                body.classification,
                body.target_scope,
                body.reason,
                body.client_request_id,
            ),
        )

    async def decide_import(self, ctx, import_id: UUID, body: DecideDataImport, trace_id: UUID):
        return await self.rpc(
            ctx,
            'data_import_decide',
            (
                ctx.session_id,
                trace_id,
                ctx.tenant_id,
                import_id,
                body.decision,
                body.comment,
                body.expected_revision,
            ),
        )

    async def list_imports(self, ctx, status: str | None = None):
        return await self.rpc(ctx, 'data_import_list', (ctx.session_id, ctx.tenant_id, status))


@router.post('/data-imports')
async def create_import_request(request: Request, body: CreateDataImport):
    ctx = await context(request, write=True)
    repo = DataImportRepository(request.app.state.pool)
    data = await repo.request_import(ctx, body, UUID(request.state.request_id))
    return response(request, data, status_code=201)


@router.get('/admin/data-imports')
async def list_import_requests(request: Request, status: str | None = None):
    ctx = await context(request, write=False)
    repo = DataImportRepository(request.app.state.pool)
    data = await repo.list_imports(ctx, status)
    return response(request, data)


@router.post('/admin/data-imports/{import_id}/decisions')
async def decide_import_request(request: Request, import_id: UUID, body: DecideDataImport):
    ctx = await context(request, write=True)
    repo = DataImportRepository(request.app.state.pool)
    data = await repo.decide_import(ctx, import_id, body, UUID(request.state.request_id))
    return response(request, data, status_code=200)
