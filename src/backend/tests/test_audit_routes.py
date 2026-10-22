"""Unit tests for /admin/tool-audit and /admin/tool-health routes."""
import json
from types import SimpleNamespace
from uuid import UUID, uuid4
import pytest

from app.errors import AppError
from app.tools import routes
from app.tools.audit import AuditLedgerService
from app.tools.dispatch import ConnectorDispatcher
from app.tools.resilience import CircuitBreaker


@pytest.mark.anyio
async def test_tool_audit_route_permissions_and_filtering(monkeypatch):
    tenant_id = UUID("11111111-1111-4111-8111-111111111111")
    user_id = UUID("22222222-2222-4222-8222-222222222222")

    audit_svc = AuditLedgerService()
    await audit_svc.append(
        tenant_id=str(tenant_id),
        actor_id=str(user_id),
        trace_id="tr-test-1",
        tool_id="credit_lookup",
        event_type="invocation",
        argument_digest="abc",
    )

    # 1. Non-admin role raises FORBIDDEN (403)
    user_ctx = SimpleNamespace(role="user", tenant_id=tenant_id, user_id=user_id)
    req_user = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(audit_service=audit_svc)),
        query_params={},
        state=SimpleNamespace(request_id="req-user", tenant_id=str(tenant_id)),
    )
    async def fake_user_context(r):
        return user_ctx

    monkeypatch.setattr(routes, "context", fake_user_context)

    with pytest.raises(AppError) as exc_info:
        await routes.list_tool_audit(req_user)
    assert exc_info.value.code == "FORBIDDEN"
    assert exc_info.value.status == 403

    # 2. Tenant Admin succeeds and returns items (200)
    admin_ctx = SimpleNamespace(role="tenant_admin", tenant_id=tenant_id, user_id=user_id)
    req_admin = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(audit_service=audit_svc)),
        query_params={"tool_id": "credit_lookup"},
        state=SimpleNamespace(request_id="req-admin", tenant_id=str(tenant_id)),
    )

    async def fake_admin_context(r):
        return admin_ctx

    monkeypatch.setattr(routes, "context", fake_admin_context)

    resp = await routes.list_tool_audit(req_admin)
    data = json.loads(resp.body.decode("utf-8"))
    assert data["data"]["count"] == 1
    assert data["data"]["items"][0]["tool_id"] == "credit_lookup"
    assert data["data"]["items"][0]["event_type"] == "invocation"


@pytest.mark.anyio
async def test_tool_health_route(monkeypatch):
    tenant_id = UUID("11111111-1111-4111-8111-111111111111")
    user_id = UUID("22222222-2222-4222-8222-222222222222")

    cb = CircuitBreaker()
    dispatcher = ConnectorDispatcher(circuit_breaker=cb)

    admin_ctx = SimpleNamespace(role="platform_admin", tenant_id=tenant_id, user_id=user_id)
    req_health = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(dispatcher=dispatcher)),
        query_params={"tool_id": "payment_gateway"},
        state=SimpleNamespace(request_id="req-health", tenant_id=str(tenant_id)),
    )

    async def fake_health_context(r):
        return admin_ctx

    monkeypatch.setattr(routes, "context", fake_health_context)

    resp = await routes.get_tool_health(req_health)
    data = json.loads(resp.body.decode("utf-8"))
    assert data["data"]["tool_id"] == "payment_gateway"
    assert data["data"]["circuit_state"] == "closed"
    assert data["data"]["status"] == "healthy"
