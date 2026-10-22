"""Unit tests for ConnectorDispatcher."""
import pytest
import httpx

from app.errors import AppError
from app.tools.audit import AuditLedgerService
from app.tools.connectors.openapi_connector import OpenAPIConnector
from app.tools.dispatch import ConnectorDispatcher
from app.tools.resilience import CircuitBreaker, TokenBucketRateLimiter


@pytest.mark.anyio
async def test_dispatcher_success_flow():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"balance": 1000})

    connector = OpenAPIConnector(transport=httpx.MockTransport(handler))
    audit_svc = AuditLedgerService()
    dispatcher = ConnectorDispatcher(
        audit_service=audit_svc,
        connectors={"openapi": connector},
    )

    tenant_id = "11111111-1111-1111-1111-111111111111"
    actor_id = "22222222-2222-2222-2222-222222222222"
    trace_id = "trace-disp-1"

    result = await dispatcher.dispatch(
        tenant_id=tenant_id,
        actor_id=actor_id,
        trace_id=trace_id,
        tool_id="get_balance",
        source_type="openapi",
        endpoint_url="https://api.bank.internal",
        credential_ref="token-secret",
        tool_meta={"method": "GET", "path": "/balance"},
        arguments={},
    )

    assert result.status == "success"
    assert result.body == {"balance": 1000}

    # Verify audit events: invocation and result
    events = audit_svc.get_events(tenant_id, trace_id=trace_id)
    assert len(events) == 2
    types = [e.event_type for e in events]
    assert "invocation" in types
    assert "result" in types


@pytest.mark.anyio
async def test_dispatcher_rate_limited():
    limiter = TokenBucketRateLimiter(default_max_tokens=1)
    audit_svc = AuditLedgerService()
    dispatcher = ConnectorDispatcher(
        rate_limiter=limiter,
        audit_service=audit_svc,
    )

    tenant_id = "t1"
    actor_id = "a1"

    # 1st call consumes token
    limiter.try_acquire(tenant_id, "rate_tool", max_tokens=1)

    # 2nd call should raise TOOL_RATE_LIMITED
    with pytest.raises(AppError) as exc_info:
        await dispatcher.dispatch(
            tenant_id=tenant_id,
            actor_id=actor_id,
            trace_id="tr-rate",
            tool_id="rate_tool",
            source_type="openapi",
            endpoint_url="https://api.bank.internal",
            credential_ref=None,
            tool_meta={"method": "GET", "path": "/test"},
            arguments={},
            rate_limit_per_minute=1,
        )
    assert exc_info.value.code == "TOOL_RATE_LIMITED"
    assert exc_info.value.status == 429

    events = audit_svc.get_events(tenant_id, tool_id="rate_tool")
    assert any(e.event_type == "rate_limit" and e.status == "blocked" for e in events)


@pytest.mark.anyio
async def test_dispatcher_circuit_breaker_open():
    cb = CircuitBreaker(failure_threshold=1)
    audit_svc = AuditLedgerService()

    def handler_fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "fatal"})

    connector = OpenAPIConnector(transport=httpx.MockTransport(handler_fail))
    dispatcher = ConnectorDispatcher(
        circuit_breaker=cb,
        audit_service=audit_svc,
        connectors={"openapi": connector},
    )

    tenant_id = "t2"
    actor_id = "a2"

    # 1st call fails
    res = await dispatcher.dispatch(
        tenant_id=tenant_id,
        actor_id=actor_id,
        trace_id="tr-cb-1",
        tool_id="cb_tool",
        source_type="openapi",
        endpoint_url="https://api.bank.internal",
        credential_ref=None,
        tool_meta={"method": "GET", "path": "/fail"},
        arguments={},
    )
    assert res.status == "failed"

    # Circuit should now be open -> next call blocked with 503
    with pytest.raises(AppError) as exc_info:
        await dispatcher.dispatch(
            tenant_id=tenant_id,
            actor_id=actor_id,
            trace_id="tr-cb-2",
            tool_id="cb_tool",
            source_type="openapi",
            endpoint_url="https://api.bank.internal",
            credential_ref=None,
            tool_meta={"method": "GET", "path": "/fail"},
            arguments={},
        )
    assert exc_info.value.code == "TOOL_CIRCUIT_OPEN"
    assert exc_info.value.status == 503
