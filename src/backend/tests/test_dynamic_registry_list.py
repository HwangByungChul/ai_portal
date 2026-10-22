"""Database-free contract coverage for the dedicated registry list RPC."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID

import psycopg
import pytest

from app.errors import AppError
from app.tools import dynamic_repository


@pytest.mark.parametrize("items", [[], [
    {"tool_id": "alpha_tool", "name": "Alpha", "revision_number": 2},
    {"tool_id": "beta_tool", "name": "Beta", "revision_number": 1},
]])
def test_list_uses_tenant_authorized_rpc_and_returns_entire_items_array(monkeypatch, items):
    ctx = SimpleNamespace(
        session_id=UUID("11111111-1111-4111-8111-111111111111"),
        tenant_id=UUID("22222222-2222-4222-8222-222222222222"),
    )
    pool = object()
    calls = []

    class Result:
        async def fetchone(self):
            return {"data": {"items": items}}

    class Connection:
        async def execute(self, query, parameters):
            calls.append((query, parameters))
            return Result()

    @asynccontextmanager
    async def transaction(actual_pool, actual_ctx):
        assert actual_pool is pool
        assert actual_ctx is ctx
        yield Connection()

    monkeypatch.setattr(dynamic_repository, "tenant_transaction", transaction)

    result = asyncio.run(dynamic_repository.DynamicToolRepository(pool).list(ctx))

    assert calls == [(
        "SELECT security.mcp_tool_registry_list(%s,%s) AS data",
        (ctx.session_id, ctx.tenant_id),
    )]
    assert result == items


class ForbiddenDatabaseError(psycopg.Error):
    sqlstate = "A0403"


@pytest.mark.parametrize("error,code", [
    (ValueError("CONTEXT_UNAVAILABLE"), "TENANT_FORBIDDEN"),
    (ForbiddenDatabaseError("FORBIDDEN"), "REQUEST_FORBIDDEN"),
])
def test_list_preserves_repository_error_translation(monkeypatch, error, code):
    @asynccontextmanager
    async def transaction(pool, ctx):
        raise error
        yield  # pragma: no cover

    monkeypatch.setattr(dynamic_repository, "tenant_transaction", transaction)

    with pytest.raises(AppError) as caught:
        asyncio.run(dynamic_repository.DynamicToolRepository(object()).list(object()))

    assert caught.value.code == code
    assert caught.value.status == 403
