"""Tests for POST /api/v1/tools/import-mcp endpoint."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4
import pytest

from app.errors import AppError
from app.tools import autowrap_routes
from app.tools.autowrap_routes import ImportMCPToolsRequest
from app.tools.transports.streamable_http import DiscoveredTool, ToolCatalog


@pytest.mark.anyio
async def test_import_mcp_non_https_rejected(monkeypatch):
    ctx = SimpleNamespace(effective_role="TADMIN", tenant_id=uuid4(), user_id=uuid4())
    req = SimpleNamespace(
        state=SimpleNamespace(request_id="req-1", tenant_id=str(ctx.tenant_id)),
    )
    async def fake_ctx(r, write=False):
        return ctx

    monkeypatch.setattr(autowrap_routes, "context", fake_ctx)

    body = ImportMCPToolsRequest(
        server_url="http://insecure.internal/sse",
        allowed_hosts=["insecure.internal"],
    )
    with pytest.raises(AppError) as exc_info:
        await autowrap_routes.import_mcp_tools(req, body)
    assert exc_info.value.code == "TOOL_ENDPOINT_INVALID"


@pytest.mark.anyio
async def test_import_mcp_disallowed_host_rejected(monkeypatch):
    ctx = SimpleNamespace(effective_role="PADMIN", tenant_id=uuid4(), user_id=uuid4())
    req = SimpleNamespace(
        state=SimpleNamespace(request_id="req-2", tenant_id=str(ctx.tenant_id)),
    )
    async def fake_ctx(r, write=False):
        return ctx

    monkeypatch.setattr(autowrap_routes, "context", fake_ctx)

    body = ImportMCPToolsRequest(
        server_url="https://attacker.com/sse",
        allowed_hosts=["trusted.internal"],
    )
    with pytest.raises(AppError) as exc_info:
        await autowrap_routes.import_mcp_tools(req, body)
    assert exc_info.value.code == "TOOL_ENDPOINT_INVALID"


@pytest.mark.anyio
async def test_import_mcp_success_and_filter(monkeypatch):
    ctx = SimpleNamespace(effective_role="PADMIN", tenant_id=uuid4(), user_id=uuid4())
    req = SimpleNamespace(
        state=SimpleNamespace(request_id="req-3", tenant_id=str(ctx.tenant_id)),
    )
    async def fake_ctx(r, write=False):
        return ctx

    monkeypatch.setattr(autowrap_routes, "context", fake_ctx)

    # Mock discover_tools to return 2 discovered tools
    mock_catalog = ToolCatalog(
        tools=(
            DiscoveredTool(
                name="balance_check",
                description="계좌 잔액 조회",
                input_schema={"type": "object", "properties": {"acc": {"type": "string"}}},
            ),
            DiscoveredTool(
                name="card_limit",
                description="카드 한도 조회",
                input_schema={"type": "object", "properties": {"card_no": {"type": "string"}}},
            ),
        ),
        sdk_source="mcp/2.3.0",
        protocol_version="2025-06-18",
        server_name="test_server",
        server_version="1.0",
    )
    from app.tools.transports import streamable_http
    monkeypatch.setattr(streamable_http, "discover_tools", AsyncMock(return_value=mock_catalog))

    body = ImportMCPToolsRequest(
        server_url="https://trusted.internal/sse",
        allowed_hosts=["trusted.internal"],
        tool_names_filter=["balance_check"],  # only import balance_check
    )

    resp = await autowrap_routes.import_mcp_tools(req, body)
    data = json.loads(resp.body.decode("utf-8"))["data"]

    assert data["status"] == "success"
    assert data["total_discovered"] == 2
    assert data["skipped_count"] == 1
    assert len(data["imported_tools"]) == 1
    assert data["imported_tools"][0]["tool_id"] == "balance_check"
