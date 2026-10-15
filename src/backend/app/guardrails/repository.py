"""Guardrail Policy & Violation Audit PostgreSQL Repository.

Backed by ops.guardrail_policy_versions, ops.guardrail_policy_heads,
ops.guardrail_violations via security.* security-definer RPC functions.
"""
import json
from uuid import UUID
from datetime import datetime
import psycopg
from app.db import tenant_transaction
from app.errors import AppError

class GuardrailRepository:
    def __init__(self, pool):
        self.pool = pool

    async def rpc(self, ctx, name: str, args: tuple):
        try:
            async with tenant_transaction(self.pool, ctx) as conn:
                placeholders = ','.join(['%s'] * len(args))
                query = f"SELECT security.{name}({placeholders}) AS data"
                row = await (await conn.execute(query, args)).fetchone()
                return row['data']
        except (psycopg.Error, ValueError) as error:
            sqlstate = getattr(error, 'sqlstate', None)
            if sqlstate == 'A0403':
                raise AppError('MANAGEMENT_DENIED', 403) from None
            if sqlstate == 'A0404':
                raise AppError('RESOURCE_NOT_FOUND', 404) from None
            if sqlstate == 'A0409':
                raise AppError('REVISION_CONFLICT', 409) from None
            if sqlstate == 'A0422':
                raise AppError('REQUEST_INVALID', 422) from None
            raise AppError('STORAGE_UNAVAILABLE', 500) from None

    async def runtime_policy(self, ctx) -> dict:
        return await self.rpc(ctx,'guardrail_runtime_policy',(ctx.session_id,ctx.tenant_id))

    async def get_policy(self, ctx) -> dict:
        """Read current policy for tenant via security.guardrail_policy_read."""
        return await self.rpc(
            ctx,
            'guardrail_policy_read',
            (ctx.session_id, ctx.tenant_id)
        )

    async def update_policy(self, ctx, trace_id: UUID, expected_revision: int, policy_dict: dict) -> dict:
        """Update policy for tenant via security.guardrail_policy_update (CAS)."""
        return await self.rpc(
            ctx,
            'guardrail_policy_update',
            (
                ctx.session_id,
                trace_id,
                ctx.tenant_id,
                expected_revision,
                json.dumps(policy_dict)
            )
        )

    async def record_violation(
        self,
        ctx,
        trace_id: UUID,
        user_id: UUID,
        run_id: UUID | None,
        direction: str,
        rule_ids: list[str],
        content_hash: str,
        policy_revision: int
    ) -> UUID:
        """Record violation via security.guardrail_violation_append."""
        result = await self.rpc(
            ctx,
            'guardrail_violation_append',
            (
                ctx.session_id,
                trace_id,
                ctx.tenant_id,
                user_id,
                run_id,
                direction,
                rule_ids,
                content_hash,
                policy_revision
            )
        )
        return UUID(str(result))

    async def list_violations(self, ctx, limit: int = 50, cursor: datetime | None = None) -> dict:
        """List recent violations via security.guardrail_violations_list."""
        return await self.rpc(
            ctx,
            'guardrail_violations_list',
            (
                ctx.session_id,
                ctx.tenant_id,
                limit,
                cursor
            )
        )
