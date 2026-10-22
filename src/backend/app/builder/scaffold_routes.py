"""Bounded owner-only API for generation and review of unsaved Builder drafts."""
from uuid import UUID
from fastapi import APIRouter, Request, Query
from app.auth.crypto import window_digest
from app.builder.scaffold_repository import ScaffoldRepository
from app.builder.scaffold_schemas import ScaffoldRequest
from app.db import tenant_transaction
from app.errors import AppError, response
from app.tenants.routes import context

router = APIRouter(prefix="/api/v1/admin/builder/scaffolds")

async def _window(request, ctx):
    settings = request.app.state.settings
    digest = window_digest(settings.login_hmac_secret.get_secret_value(), "http_read", "principal",
                           str(ctx.user_id) + ":" + str(ctx.tenant_id))
    try:
        async with tenant_transaction(request.app.state.pool, ctx) as conn:
            row = await (await conn.execute(
                "SELECT * FROM security.operations_read_window(%s,%s,%s,%s)",
                (ctx.session_id, ctx.tenant_id, "agent_admin", digest),
            )).fetchone()
    except ValueError as error:
        if error.args == ("CONTEXT_UNAVAILABLE",):
            raise AppError("AUTH_REQUIRED", 401) from None
        raise
    if row is not None and not row["allowed"]:
        raise AppError("RATE_LIMITED", 429, row["retry_after"])

@router.post("")
async def create_scaffold(request: Request, body: ScaffoldRequest):
    ctx = await context(request, write=True)
    if request.query_params:
        raise AppError("REQUEST_INVALID", 422)
    service = request.app.state.builder_scaffold
    if service is None:
        raise AppError("SERVICE_UNAVAILABLE", 503)
    await _window(request, ctx)
    trace_id = UUID(request.state.request_id)
    refs = [ref.model_dump(mode="json") for ref in body.document_refs]
    if refs:
        await request.app.state.documents.allowed(ctx, refs, request.app.state.settings.mode)
    policy = await request.app.state.guardrails.snapshot(ctx)
    repository = service.repository
    admitted = await repository.admit(ctx, body, trace_id=trace_id, model_id="gpt-4o-mini",
                                     policy_revision=policy.revision,
                                     budget_period=request.app.state.settings.budget_period)
    if admitted.get("replayed"):
        return response(request, await repository.read(ctx, UUID(admitted["proposal_id"])))
    result = await service.generate(ctx, UUID(admitted["proposal_id"]), trace_id,
                                    admitted["revision"], body)
    return response(request, result)

@router.get("/{proposal_id}")
async def get_scaffold(request: Request, proposal_id: UUID):
    ctx = await context(request)
    if request.query_params:
        raise AppError("REQUEST_INVALID", 422)
    await _window(request, ctx)
    return response(request, await ScaffoldRepository(request.app.state.pool).read(ctx, proposal_id))

@router.delete("/{proposal_id}")
async def delete_scaffold(request: Request, proposal_id: UUID,
                          expected_revision: int = Query(ge=1, le=9223372036854775807)):
    ctx = await context(request, write=True)
    if set(request.query_params) != {"expected_revision"} or len(request.query_params.getlist("expected_revision")) != 1:
        raise AppError("REQUEST_INVALID", 422)
    await _window(request, ctx)
    return response(request, await ScaffoldRepository(request.app.state.pool).discard(
        ctx, proposal_id, expected_revision))
