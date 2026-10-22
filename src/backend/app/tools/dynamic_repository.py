"""Tenant-scoped persistence for dynamically wrapped MCP tool definitions.

This repository persists registry metadata only. It does not make the endpoint
profiles executable and deliberately does not accept credentials.
"""
import psycopg
from psycopg.types.json import Jsonb

from app.db import tenant_transaction
from app.errors import AppError
from app.tenants.repository import TenantRepository


class DynamicToolRepository:
    def __init__(self, pool):
        self.pool = pool

    async def register(self, ctx, *, tool_id, name, description, source_type,
                       input_schema, raw_meta, dev_profile, prd_profile):
        """Append a schema revision through the narrow SECURITY DEFINER RPC."""
        try:
            async with tenant_transaction(self.pool, ctx) as conn:
                row = await (await conn.execute(
                    """SELECT security.mcp_tool_registry_control(
                         %s,%s,'register',%s,%s,%s,%s,%s,%s,%s,%s) AS data""",
                    (ctx.session_id, ctx.tenant_id, tool_id, name, description, source_type,
                     Jsonb(input_schema), Jsonb(raw_meta or {}), Jsonb(dev_profile), Jsonb(prd_profile)),
                )).fetchone()
            return row["data"]
        except (psycopg.Error, ValueError) as error:
            if isinstance(error, psycopg.Error) and error.sqlstate in ("22P02", "22003", "22021", "22P05"):
                raise AppError("REQUEST_INVALID", 422) from None
            TenantRepository.translate(error)

    async def list(self, ctx):
        """List the latest tenant-visible schema revision without secret fields."""
        try:
            async with tenant_transaction(self.pool, ctx) as conn:
                row = await (await conn.execute(
                    "SELECT security.mcp_tool_registry_list(%s,%s) AS data",
                    (ctx.session_id, ctx.tenant_id),
                )).fetchone()
            return row["data"].get("items", [])
        except (psycopg.Error, ValueError) as error:
            TenantRepository.translate(error)

    async def simulation_profile(self, ctx, tool_id):
        """Load persisted non-secret metadata for the mock-only invoke adapter."""
        try:
            async with tenant_transaction(self.pool, ctx) as conn:
                row = await (await conn.execute(
                    "SELECT security.mcp_tool_registry_control(%s,%s,'simulation_get',%s,NULL,NULL,NULL,NULL,NULL,NULL,NULL) AS data",
                    (ctx.session_id, ctx.tenant_id, tool_id),
                )).fetchone()
            return row["data"]
        except (psycopg.Error, ValueError) as error:
            TenantRepository.translate(error)

    async def approval_descriptor(self, ctx, tool_id, mode):
        """Return a server-computed, revision-bound descriptor for review only."""
        try:
            async with tenant_transaction(self.pool, ctx) as conn:
                row = await (await conn.execute(
                    "SELECT security.mcp_tool_approval_control(%s,%s,'describe',%s,NULL,NULL,NULL,NULL,%s) AS data",
                    (ctx.session_id, ctx.tenant_id, tool_id, mode),
                )).fetchone()
            return row["data"]
        except (psycopg.Error, ValueError) as error:
            TenantRepository.translate(error)

    async def submit_approval(self, ctx, *, tool_id, client_request_id, audience, member_ids,
                              expected_head_revision, mode):
        try:
            async with tenant_transaction(self.pool, ctx) as conn:
                row = await (await conn.execute(
                    "SELECT security.mcp_tool_approval_control(%s,%s,'submit',%s,%s,%s,%s,%s,%s) AS data",
                    (ctx.session_id, ctx.tenant_id, tool_id, client_request_id, audience,
                     Jsonb(member_ids), expected_head_revision, mode),
                )).fetchone()
            return row["data"]
        except (psycopg.Error, ValueError) as error:
            TenantRepository.translate(error)
