"""E2E Verification tests against Mock Financial Sandbox Servers.

Tests real network I/O, TLS handshakes, LRC checksum calculations,
streaming response size limits (1 MiB), timeouts, and Circuit Breaker trips.
"""
import asyncio
import os
import ssl
import httpx
import pytest
from app.errors import AppError
from app.tools.connectors.financial_packet_connector import FinancialPacketConnector
from app.tools.connectors.openapi_connector import OpenAPIConnector
from app.tools.connectors.wsdl_connector import WSDLConnector
from app.tools.dispatch import ConnectorDispatcher
from app.tools.resilience import CircuitBreaker, TokenBucketRateLimiter
from app.tools.simulation_sandbox import (
    FinancialPacketSandboxServer,
    HttpSandboxServer,
    generate_self_signed_cert,
)


@pytest.fixture(scope="module")
def tls_cert_pair():
    cert_path, key_path = generate_self_signed_cert()
    yield cert_path, key_path
    if os.path.exists(cert_path):
        os.remove(cert_path)
    if os.path.exists(key_path):
        os.remove(key_path)


@pytest.mark.anyio
async def test_financial_packet_connector_tls_e2e(tls_cert_pair):
    cert_path, key_path = tls_cert_pair
    server = FinancialPacketSandboxServer(cert_path, key_path)
    port = await server.start()
    try:
        # Use a socket factory that trusts self-signed cert on loopback
        async def mock_tls_socket(host: str, p: int, _):
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return await asyncio.open_connection(host, p, ssl=ctx)

        connector = FinancialPacketConnector(socket_factory=mock_tls_socket)

        tool_meta = {
            "layout_version": "v1",
            "encoding": "utf-8",
            "fields": [
                {"name": "header", "length": 10, "type": "str", "required": True},
                {"name": "trx_type", "length": 4, "type": "str", "required": True},
                {"name": "res_code", "length": 4, "type": "str", "required": True},
                {"name": "account_no", "length": 16, "type": "str"},
                {"name": "amount", "length": 12, "type": "str"},
                {"name": "data", "length": 33, "type": "str"},
            ],
        }

        # 1. Normal inquiry (10-14: "INQ0")
        result = await connector.execute(
            endpoint_url=f"tls://127.0.0.1:{port}",
            credential_ref=None,
            tool_meta=tool_meta,
            arguments={
                "header": "TESTBANK01",
                "trx_type": "INQ0",
                "res_code": "0000",
                "account_no": "1234567890123456",
                "amount": "000001500000",
                "data": "A" * 33,
            },
            timeout_seconds=2,
        )
        assert result.status == "success"
        assert result.body["res_code"] == "0000"
        assert result.body["trx_type"] == "INQ0"

        # 2. Error inquiry (10-14: "ERR0")
        err_result = await connector.execute(
            endpoint_url=f"tls://127.0.0.1:{port}",
            credential_ref=None,
            tool_meta=tool_meta,
            arguments={
                "header": "TESTBANK01",
                "trx_type": "ERR0",
                "res_code": "0000",
                "account_no": "1234567890123456",
                "amount": "000000000000",
                "data": "B" * 33,
            },
            timeout_seconds=2,
        )
        assert err_result.status == "success"
        assert err_result.body["res_code"] == "9999"
    finally:
        await server.stop()


@pytest.mark.anyio
async def test_openapi_connector_e2e_network(tls_cert_pair):
    cert_path, key_path = tls_cert_pair
    server = HttpSandboxServer(cert_path, key_path)
    port = await server.start()
    try:
        base_url = f"https://127.0.0.1:{port}"
        transport = httpx.AsyncHTTPTransport(verify=False)
        connector = OpenAPIConnector(transport=transport)

        # 1. Successful balance inquiry
        result = await connector.execute(
            endpoint_url=base_url,
            credential_ref="test-secret-token",
            tool_meta={
                "method": "GET",
                "path": "/api/v1/accounts/{account_id}/balance",
            },
            arguments={"account_id": "ACC1002"},
            timeout_seconds=5,
        )
        assert result.status == "success"
        assert result.body["account_id"] == "ACC1002"
        assert result.body["available_balance"] == 15000000

        # 2. 1 MiB Payload overflow test
        overflow_result = await connector.execute(
            endpoint_url=base_url,
            credential_ref=None,
            tool_meta={"method": "GET", "path": "/api/v1/large-data"},
            arguments={},
            timeout_seconds=5,
        )
        assert overflow_result.status == "failed"
        assert overflow_result.error_code == "TOOL_RESPONSE_TOO_LARGE"

        # 3. Timeout test
        timeout_result = await connector.execute(
            endpoint_url=base_url,
            credential_ref=None,
            tool_meta={"method": "GET", "path": "/api/v1/delayed"},
            arguments={},
            timeout_seconds=1,
        )
        assert timeout_result.status == "timeout"
        assert timeout_result.error_code == "TOOL_EXECUTION_TIMEOUT"
    finally:
        await server.stop()


@pytest.mark.anyio
async def test_wsdl_connector_e2e_network(tls_cert_pair):
    cert_path, key_path = tls_cert_pair
    server = HttpSandboxServer(cert_path, key_path)
    port = await server.start()
    try:
        base_url = f"https://127.0.0.1:{port}"
        transport = httpx.AsyncHTTPTransport(verify=False)
        connector = WSDLConnector(transport=transport)

        result = await connector.execute(
            endpoint_url=f"{base_url}/soap/AccountService",
            credential_ref=None,
            tool_meta={
                "operation": "GetAccountBalance",
                "soap_action": "GetAccountBalance",
                "allowed_actions": ["GetAccountBalance"],
            },
            arguments={"account_id": "ACC999"},
            timeout_seconds=5,
        )
        assert result.status == "success"
        assert result.body["Balance"] == "25000000"
        assert result.body["Currency"] == "KRW"
    finally:
        await server.stop()


@pytest.mark.anyio
async def test_connector_dispatcher_circuit_breaker_trip(tls_cert_pair):
    cert_path, key_path = tls_cert_pair
    server = HttpSandboxServer(cert_path, key_path)
    port = await server.start()
    try:
        base_url = f"https://127.0.0.1:{port}"
        transport = httpx.AsyncHTTPTransport(verify=False)
        openapi_conn = OpenAPIConnector(transport=transport)

        cb = CircuitBreaker(failure_threshold=2, recovery_timeout_seconds=5.0)
        limiter = TokenBucketRateLimiter(default_max_tokens=100, default_refill_per_sec=100.0)
        dispatcher = ConnectorDispatcher(
            rate_limiter=limiter,
            circuit_breaker=cb,
            connectors={"openapi": openapi_conn},
        )

        # Call failing endpoint 2 times
        for _ in range(2):
            res = await dispatcher.dispatch(
                tenant_id="tenant-alpha",
                actor_id="user-1",
                trace_id="trace-1",
                tool_id="failing_tool",
                source_type="openapi",
                endpoint_url=base_url,
                credential_ref=None,
                tool_meta={"method": "GET", "path": "/api/v1/failing"},
                arguments={},
                timeout_seconds=5,
            )
            assert res.status == "failed"

        assert cb.state("tenant-alpha", "failing_tool") == "open"

        # 3rd call must be short-circuited immediately
        with pytest.raises(AppError) as exc_info:
            await dispatcher.dispatch(
                tenant_id="tenant-alpha",
                actor_id="user-1",
                trace_id="trace-1",
                tool_id="failing_tool",
                source_type="openapi",
                endpoint_url=base_url,
                credential_ref=None,
                tool_meta={"method": "GET", "path": "/api/v1/failing"},
                arguments={},
                timeout_seconds=5,
            )
        assert exc_info.value.code == "TOOL_CIRCUIT_OPEN"
    finally:
        await server.stop()
