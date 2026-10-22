"""DP-16: Role SOD service — grant/revoke extended roles with SOD enforcement.

Extended roles: BUILDER (draft), REVIEWER (review), DEPLOYER (deploy)
These roles are additive on top of the base USER/TADMIN/PADMIN system.
SOD rules: BUILDER cannot coexist with REVIEWER or DEPLOYER.
"""
from __future__ import annotations

from uuid import UUID

import psycopg

from app.db import tenant_transaction
from app.errors import AppError


class RoleSODRepository:
    """DB facade for DP-16 role grant/revoke operations."""

    def __init__(self, pool):
        self.pool = pool

    def _translate(self, error: Exception) -> None:
        sqlstate = getattr(error, "sqlstate", None)
        mapping = {
            "A0403": ("REQUEST_FORBIDDEN", 403),
            "A0404": ("GRANT_NOT_FOUND", 404),
            "A0409": ("ROLE_SOD_CONFLICT", 409),
        }
        if sqlstate in mapping:
            raise AppError(*mapping[sqlstate]) from None
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

    async def grant(self, ctx, target_user_id: UUID, role_code: str,
                    expires_at=None) -> str:
        data = await self._rpc(ctx, "role_grant", (
            ctx.session_id, ctx.tenant_id, target_user_id, role_code, expires_at,
        ))
        return data["grant_id"]

    async def revoke(self, ctx, target_user_id: UUID, role_code: str,
                     note: str = "") -> None:
        await self._rpc(ctx, "role_revoke", (
            ctx.session_id, ctx.tenant_id, target_user_id, role_code, note,
        ))

    async def list_roles(self, ctx, target_user_id: UUID) -> list[dict]:
        data = await self._rpc(ctx, "role_list_for_user", (
            ctx.session_id, ctx.tenant_id, target_user_id,
        ))
        return data.get("roles", [])
