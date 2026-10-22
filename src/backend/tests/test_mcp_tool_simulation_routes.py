"""Request-local simulation contracts; no database, HTTP service, or connector."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.errors import AppError
from app.tools import autowrap_routes as routes


def definition():
    return {
        "tool_id": "fixture_tool", "name": "Fixture", "description": "unsaved",
        "source_type": "openapi", "input_schema": {"type": "object", "required": ["amount"]},
        "raw_meta": {}, "arguments": {"amount": 10},
        "dev_profile": {"protocol_type": "rest_http", "base_endpoint_url": "https://example.invalid/dev"},
    }


def request():
    return SimpleNamespace(state=SimpleNamespace(request_id="simulation-test", tenant_id="tenant-a"))


@pytest.mark.parametrize("role", ["TADMIN", "PADMIN"])
def test_unsaved_simulation_never_accesses_registry_or_shared_gateway(monkeypatch, role):
    actual_request = request()
    ctx = SimpleNamespace(effective_role=role, tenant_id="tenant-a", user_id="user-a")
    context_calls = []

    async def context(req, *, write):
        assert req is actual_request
        context_calls.append(write)
        return ctx

    def forbidden(*args, **kwargs):
        pytest.fail("simulation must not touch the durable repository or shared registry")

    monkeypatch.setattr(routes, "context", context)
    monkeypatch.setattr(routes, "DynamicToolRepository", forbidden)
    monkeypatch.setattr(routes.GLOBAL_DYNAMIC_TOOL_GATEWAY, "register_tool", forbidden)
    tools_before = deepcopy(routes.GLOBAL_DYNAMIC_TOOL_GATEWAY._tools)
    profiles_before = deepcopy(routes.GLOBAL_DYNAMIC_TOOL_GATEWAY._profiles)
    audit_before = deepcopy(routes.GLOBAL_DYNAMIC_TOOL_GATEWAY._audit_logs)

    async def checks():
        for amount in (10, 20):
            body = routes.AutoWrapSimulateRequest(**(definition() | {"arguments": {"amount": amount}}))
            result = await routes.simulate_auto_wrapped_tool(actual_request, body)
            payload = json.loads(result.body)["data"]
            assert result.status_code == 200
            assert payload["routed_env"] == "development"
            assert payload["result"]["applied_arguments"] == {"amount": amount}

    asyncio.run(checks())
    assert context_calls == [True, True]
    assert routes.GLOBAL_DYNAMIC_TOOL_GATEWAY._tools == tools_before
    assert routes.GLOBAL_DYNAMIC_TOOL_GATEWAY._profiles == profiles_before
    assert routes.GLOBAL_DYNAMIC_TOOL_GATEWAY._audit_logs == audit_before


def test_non_admin_is_rejected_before_constructing_simulation(monkeypatch):
    async def context(req, *, write):
        assert write is True
        return SimpleNamespace(effective_role="USER")

    monkeypatch.setattr(routes, "context", context)
    monkeypatch.setattr(routes, "DynamicToolGateway", lambda: pytest.fail("must authorize first"))
    with pytest.raises(AppError) as caught:
        asyncio.run(routes.simulate_auto_wrapped_tool(request(), routes.AutoWrapSimulateRequest(**definition())))
    assert (caught.value.code, caught.value.status) == ("TOOL_NOT_PERMITTED", 403)


def test_simulation_preserves_session_csrf_failure(monkeypatch):
    async def context(req, *, write):
        assert write is True
        raise AppError("REQUEST_FORBIDDEN", 403)

    monkeypatch.setattr(routes, "context", context)
    monkeypatch.setattr(routes, "DynamicToolGateway", lambda: pytest.fail("must authorize first"))
    with pytest.raises(AppError) as caught:
        asyncio.run(routes.simulate_auto_wrapped_tool(request(), routes.AutoWrapSimulateRequest(**definition())))
    assert caught.value.code == "REQUEST_FORBIDDEN"


def test_invalid_simulation_arguments_remain_rejected(monkeypatch):
    async def context(req, *, write):
        return SimpleNamespace(effective_role="TADMIN", tenant_id="tenant-a", user_id="user-a")

    monkeypatch.setattr(routes, "context", context)
    body = routes.AutoWrapSimulateRequest(**(definition() | {"arguments": {}}))
    with pytest.raises(AppError) as caught:
        asyncio.run(routes.simulate_auto_wrapped_tool(request(), body))
    assert (caught.value.code, caught.value.status) == ("TOOL_ARGUMENTS_INVALID", 422)


@pytest.mark.parametrize("extra", [
    {"publication_status": "approved_published"}, {"asset_id": "client-asset"},
    {"prd_profile": {"protocol_type": "rest_http", "base_endpoint_url": "https://example.invalid/prd"}},
])
def test_transient_request_rejects_production_routing_authority(extra):
    with pytest.raises(ValidationError):
        routes.AutoWrapSimulateRequest(**(definition() | extra))
