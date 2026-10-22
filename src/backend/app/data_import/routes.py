"""DP-17: Data Import Approval HTTP routes.

Endpoints:
    POST /api/v1/data-imports                             Submit import request (any authenticated user)
    GET  /api/v1/data-imports                             List own requests
    GET  /api/v1/admin/data-imports                       Admin: list all by status
    PUT  /api/v1/admin/data-imports/{id}/decide           Approve or reject (PADMIN/TADMIN; no self-approve)
"""
from __future__ import annotations

import hashlib
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, StrictStr, StrictInt
from psycopg.types.json import Jsonb

from app.data_import.scanner import auto_scan
from app.db import tenant_transaction
from app.errors import AppError, response
from app.tenants.routes import context

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class DataImportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename:     StrictStr = Field(min_length=1, max_length=255)
    mime_type:    StrictStr | None = None
    sha256:       StrictStr = Field(min_length=64, max_length=64)
    file_size:    StrictInt = Field(ge=0, le=500 * 1024 * 1024)  # max 500 MB
    import_type:  Literal["model", "document", "dataset"] = "document"
    content_sample: StrictStr = Field(default="", max_length=4000)  # first chars for PII scan


class DataImportDecide(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision:   Literal["approved", "rejected"]
    note:       StrictStr = Field(default="", max_length=500)
    cas_token:  StrictInt = Field(ge=1)


# ---------------------------------------------------------------------------
# Repository helper
# ---------------------------------------------------------------------------

class _ImportRepo:
    def __init__(self, pool):
        self.pool = pool

    def _translate(self, error: Exception) -> None:
        sqlstate = getattr(error, "sqlstate", None)
        codes = {
            "A0403": ("REQUEST_FORBIDDEN", 403),
            "A0404": ("IMPORT_NOT_FOUND", 404),
            "A0409": ("IMPORT_CONFLICT", 409),
        }
        if sqlstate in codes:
            raise AppError(*codes[sqlstate]) from None
        raise AppError("INTERNAL_ERROR", 500) from error

    async def rpc(self, ctx, func: str, args: tuple):
        try:
            async with tenant_transaction(self.pool, ctx) as conn:
                row = await (
                    await conn.execute(
                        f"SELECT security.{func}({','.join(['%s'] * len(args))}) AS data",
                        args,
                    )
                ).fetchone()
                return row["data"]
        except (psycopg.Error, ValueError) as exc:
            self._translate(exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/data-imports")
async def create_import(request: Request, body: DataImportCreate):
    """Submit a data import request with automatic pre-scan."""
    ctx = await context(request)
    pool = getattr(getattr(request.app.state, "pool", None), "pool", None)
    if pool is None:
        raise AppError("DB_UNAVAILABLE", 503)
    repo = _ImportRepo(pool)

    # Run automatic scans
    pii, fmt, mal, all_passed = auto_scan(
        body.filename, body.mime_type, body.sha256, body.content_sample
    )

    # Determine initial status
    # If format or malware fails → auto-reject; otherwise move to review
    status = "review" if all_passed else "rejected"
    if not fmt["passed"] or not mal["passed"]:
        status = "rejected"
    elif not pii["passed"]:
        # PII detected → needs human review anyway
        status = "review"

    # Create request
    data = await repo.rpc(ctx, "data_import_create", (
        ctx.session_id, ctx.tenant_id,
        body.import_type, body.filename, body.mime_type, body.sha256, body.file_size,
    ))
    import_id = data["import_id"]

    # Record scan results
    if pool:
        try:
            await repo.rpc(ctx, "data_import_set_scan", (
                ctx.session_id, ctx.tenant_id, UUID(import_id),
                Jsonb(pii), Jsonb(fmt), Jsonb(mal), status,
            ))
        except AppError:
            pass  # If scan update fails, request remains in pending

    return response(request, {
        "import_id": import_id,
        "status":    status,
        "scan": {
            "pii_passed":    pii["passed"],
            "format_passed": fmt["passed"],
            "malware_passed": mal["passed"],
        },
    })


@router.get("/data-imports")
async def list_my_imports(request: Request, status: str | None = None, limit: int = 20):
    """List the authenticated user's own import requests."""
    ctx = await context(request)
    pool = getattr(getattr(request.app.state, "pool", None), "pool", None)
    if pool is None:
        raise AppError("DB_UNAVAILABLE", 503)
    repo = _ImportRepo(pool)
    data = await repo.rpc(ctx, "data_import_list", (
        ctx.session_id, ctx.tenant_id, status, min(limit, 50),
    ))
    return response(request, {"items": data.get("items", [])})


@router.get("/admin/data-imports")
async def list_all_imports(request: Request, status: str | None = None, limit: int = 20):
    """Admin: list all import requests. PADMIN/TADMIN only."""
    ctx = await context(request)
    if ctx.effective_role not in ("PADMIN", "TADMIN"):
        raise AppError("REQUEST_FORBIDDEN", 403)
    pool = getattr(getattr(request.app.state, "pool", None), "pool", None)
    if pool is None:
        raise AppError("DB_UNAVAILABLE", 503)
    repo = _ImportRepo(pool)
    data = await repo.rpc(ctx, "data_import_list", (
        ctx.session_id, ctx.tenant_id, status, min(limit, 50),
    ))
    return response(request, {"items": data.get("items", [])})


@router.put("/admin/data-imports/{import_id}/decide")
async def decide_import(request: Request, import_id: UUID, body: DataImportDecide):
    """Approve or reject an import request. PADMIN/TADMIN only. Self-approve blocked."""
    ctx = await context(request)
    if ctx.effective_role not in ("PADMIN", "TADMIN"):
        raise AppError("REQUEST_FORBIDDEN", 403)
    pool = getattr(getattr(request.app.state, "pool", None), "pool", None)
    if pool is None:
        raise AppError("DB_UNAVAILABLE", 503)
    repo = _ImportRepo(pool)
    data = await repo.rpc(ctx, "data_import_decide", (
        ctx.session_id, ctx.tenant_id, import_id,
        body.decision, body.note, body.cas_token,
    ))
    return response(request, {"ok": True, "decision": body.decision})
