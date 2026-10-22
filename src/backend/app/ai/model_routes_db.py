"""DP-13: Extended Model Registry HTTP routes (DB-backed).

Endpoints:
    GET  /api/v1/models                       User-facing: active models
    GET  /api/v1/admin/models                 Admin: all models (PADMIN only)
    POST /api/v1/admin/models                 Register / update a model (PADMIN only)
    PUT  /api/v1/admin/models/{model_id}/active   Activate / deactivate
    PUT  /api/v1/admin/models/{model_id}/default  Set as default

Existing GET /api/v1/models and GET /api/v1/admin/models are overridden here
to prefer DB-stored entries while falling back to the in-memory GLOBAL_REGISTRY.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator

from app.ai.model_registry import GLOBAL_REGISTRY
from app.ai.model_registry_db import ModelRegistryRepository
from app.errors import AppError, response
from app.tenants.routes import context

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class ModelUpsertBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_key:    Literal["openai", "anthropic", "google", "mock"]
    model_name:      StrictStr = Field(min_length=1, max_length=120)
    display_name:    StrictStr = Field(min_length=1, max_length=80)
    context_window:  StrictInt = Field(ge=1024, le=2_000_000)
    max_output:      StrictInt = Field(ge=64,   le=1_000_000)
    price_input_usd: StrictStr = Field(default="0")   # string to avoid float imprecision
    price_out_usd:   StrictStr = Field(default="0")
    credential_ref:  StrictStr = Field(min_length=1, max_length=80)
    capabilities:    list[Literal["chat","rag","structured","streaming","vision"]] = Field(
        default=["chat", "streaming"], min_length=1
    )

    @field_validator("price_input_usd", "price_out_usd")
    @classmethod
    def validate_price(cls, v: str) -> str:
        try:
            d = Decimal(v)
        except InvalidOperation:
            raise ValueError("PRICE_INVALID") from None
        if d < 0:
            raise ValueError("PRICE_NEGATIVE")
        return v


class ModelActiveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: StrictBool


# ---------------------------------------------------------------------------
# Route helpers
# ---------------------------------------------------------------------------

def _get_repo(request: Request) -> ModelRegistryRepository | None:
    pool = getattr(getattr(request.app.state, "pool", None), "pool", None)
    if pool is None:
        return None
    return ModelRegistryRepository(pool)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_models_db(request: Request):
    """User-facing: list active models. DB-preferred, in-memory fallback."""
    ctx = await context(request)
    repo = _get_repo(request)
    if repo is not None:
        try:
            rows = await repo.list_active(ctx)
            if rows:
                return response(request, {"items": [r.to_public_dict() for r in rows]})
        except AppError:
            pass
    # Fallback to in-memory registry
    return response(request, {"items": GLOBAL_REGISTRY.list_public()})


@router.get("/admin/models")
async def list_admin_models_db(request: Request):
    """Admin: all models including inactive. PADMIN only."""
    ctx = await context(request)
    if ctx.effective_role != "PADMIN":
        raise AppError("REQUEST_FORBIDDEN", 403)
    repo = _get_repo(request)
    if repo is not None:
        rows = await repo.list_all_admin(ctx)
        return response(request, {"items": [r.to_admin_dict() for r in rows]})
    return response(request, {"items": GLOBAL_REGISTRY.list_all_admin()})


@router.post("/admin/models")
async def upsert_model(request: Request, body: ModelUpsertBody):
    """Register or update a model entry. PADMIN only."""
    ctx = await context(request)
    if ctx.effective_role != "PADMIN":
        raise AppError("REQUEST_FORBIDDEN", 403)
    repo = _get_repo(request)
    if repo is None:
        raise AppError("DB_UNAVAILABLE", 503)
    model_id = await repo.upsert(
        ctx,
        provider_key=body.provider_key,
        model_name=body.model_name,
        display_name=body.display_name,
        context_window=body.context_window,
        max_output=body.max_output,
        price_input_usd=Decimal(body.price_input_usd),
        price_out_usd=Decimal(body.price_out_usd),
        credential_ref=body.credential_ref,
        capabilities=body.capabilities,
    )
    return response(request, {"model_id": model_id})


@router.put("/admin/models/{model_id}/active")
async def set_model_active(request: Request, model_id: UUID, body: ModelActiveBody):
    """Activate or deactivate a model. PADMIN only."""
    ctx = await context(request)
    if ctx.effective_role != "PADMIN":
        raise AppError("REQUEST_FORBIDDEN", 403)
    repo = _get_repo(request)
    if repo is None:
        raise AppError("DB_UNAVAILABLE", 503)
    await repo.set_active(ctx, model_id, body.active)
    return response(request, {"ok": True})


@router.put("/admin/models/{model_id}/default")
async def set_model_default(request: Request, model_id: UUID):
    """Set a model as the tenant default. Model must be active. PADMIN only."""
    ctx = await context(request)
    if ctx.effective_role != "PADMIN":
        raise AppError("REQUEST_FORBIDDEN", 403)
    repo = _get_repo(request)
    if repo is None:
        raise AppError("DB_UNAVAILABLE", 503)
    await repo.set_default(ctx, model_id)
    return response(request, {"ok": True})
