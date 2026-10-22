"""DP-13: Model Registry — DB-backed extension of the in-memory APPROVED_MODELS registry.

Runtime strategy:
  1. On startup the in-memory GLOBAL_REGISTRY (model_registry.py) is always available.
  2. If a DB pool is provided, DB-stored active models are merged/overridden on top.
  3. credential_ref is an environment-variable name; actual key is resolved at runtime.
  4. Disabled / retired DB models shadow in-memory entries.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from app.db import tenant_transaction
from app.errors import AppError


# ---------------------------------------------------------------------------
# Domain value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DBModelRow:
    model_id: str
    provider_key: str
    model_name: str
    display_name: str
    context_window: int
    max_output: int
    price_input_usd: Decimal
    price_out_usd: Decimal
    credential_ref: str
    active: bool
    is_default: bool
    capabilities: tuple[str, ...]

    def to_public_dict(self) -> dict[str, Any]:
        """credential_ref MUST NOT be exposed to any client."""
        return {
            "model_id":       self.model_id,
            "provider_key":   self.provider_key,
            "model_name":     self.model_name,
            "display_name":   self.display_name,
            "context_window": self.context_window,
            "max_output":     self.max_output,
            "is_default":     self.is_default,
            "active":         self.active,
            "capabilities":   list(self.capabilities),
        }

    def to_admin_dict(self) -> dict[str, Any]:
        """Admin view includes pricing; credential_ref is still excluded (env-var name only)."""
        return {
            **self.to_public_dict(),
            "price_input_usd": str(self.price_input_usd),
            "price_out_usd":   str(self.price_out_usd),
            "credential_ref":  self.credential_ref,
        }


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class ModelRegistryRepository:
    """DB-backed model registry operations (RPC facade)."""

    def __init__(self, pool):
        self.pool = pool

    def _translate(self, error: Exception) -> None:
        sqlstate = getattr(error, "sqlstate", None)
        codes = {
            "A0403": ("REQUEST_FORBIDDEN", 403),
            "A0404": ("MODEL_NOT_FOUND", 404),
            "A0409": ("MODEL_CONFLICT", 409),
            "A0422": ("MODEL_NOT_ACTIVE", 422),
        }
        if sqlstate in codes:
            raise AppError(*codes[sqlstate]) from None
        raise AppError("INTERNAL_ERROR", 500) from error

    async def _rpc(self, ctx, func: str, args: tuple):
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

    async def list_active(self, ctx) -> list[DBModelRow]:
        data = await self._rpc(ctx, "model_registry_list", (ctx.session_id, ctx.tenant_id))
        return [self._parse(r) for r in (data.get("items") or [])]

    async def list_all_admin(self, ctx) -> list[DBModelRow]:
        data = await self._rpc(ctx, "model_registry_admin_list", (ctx.session_id, ctx.tenant_id))
        return [self._parse(r) for r in (data.get("items") or [])]

    async def upsert(self, ctx, *, provider_key: str, model_name: str, display_name: str,
                     context_window: int, max_output: int,
                     price_input_usd: Decimal, price_out_usd: Decimal,
                     credential_ref: str, capabilities: list[str]) -> str:
        data = await self._rpc(ctx, "model_registry_upsert", (
            ctx.session_id, ctx.tenant_id,
            provider_key, model_name, display_name,
            context_window, max_output,
            price_input_usd, price_out_usd,
            credential_ref, capabilities,
        ))
        return data["model_id"]

    async def set_active(self, ctx, model_id: UUID, active: bool) -> None:
        await self._rpc(ctx, "model_registry_set_active", (
            ctx.session_id, ctx.tenant_id, model_id, active,
        ))

    async def set_default(self, ctx, model_id: UUID) -> None:
        await self._rpc(ctx, "model_registry_set_default", (
            ctx.session_id, ctx.tenant_id, model_id,
        ))

    @staticmethod
    def _parse(row: dict) -> DBModelRow:
        return DBModelRow(
            model_id=row["model_id"],
            provider_key=row["provider_key"],
            model_name=row["model_name"],
            display_name=row.get("display_name", row["model_name"]),
            context_window=row.get("context_window", 128000),
            max_output=row.get("max_output", 4096),
            price_input_usd=Decimal(str(row.get("price_input_usd", "0"))),
            price_out_usd=Decimal(str(row.get("price_out_usd", "0"))),
            credential_ref=row.get("credential_ref", "OPENAI_API_KEY"),
            active=bool(row.get("active", True)),
            is_default=bool(row.get("is_default", False)),
            capabilities=tuple(row.get("capabilities", ["chat", "streaming"])),
        )
