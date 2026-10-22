"""Contract tests for OpenAPIConnector using httpx.MockTransport.

Zero external network calls; enforces strict boundary constraints.
"""
import pytest
import httpx

from app.errors import AppError
from app.tools.connectors.openapi_connector import OpenAPIConnector


@pytest.mark.anyio
async def test_openapi_connector_success_get():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.scheme == "https"
        assert request.url.path == "/api/v1/accounts/acc_123"
        assert request.url.query.decode() == "view=detail"
        assert request.headers["Accept"] == "application/json"
        assert request.headers["Authorization"] == "Bearer mock_token_secret"
        return httpx.Response(
            status_code=200,
            json={"account_id": "acc_123", "balance": 50000},
            headers={"Content-Type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    connector = OpenAPIConnector(transport=transport)

    tool_meta = {
        "method": "GET",
        "path": "/api/v1/accounts/{account_id}",
    }
    arguments = {
        "account_id": "acc_123",
        "view": "detail",
    }

    result = await connector.execute(
        endpoint_url="https://api.bank.internal",
        credential_ref="mock_token_secret",
        tool_meta=tool_meta,
        arguments=arguments,
        timeout_seconds=5,
    )

    assert result.status == "success"
    assert result.http_status == 200
    assert result.body == {"account_id": "acc_123", "balance": 50000}
    assert result.error_code is None
    assert len(result.redacted_digest) == 64
    assert result.retryable is False


@pytest.mark.anyio
async def test_openapi_connector_success_post():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/transfers"
        assert request.headers["Content-Type"] == "application/json"
        body = httpx.Response(200, json={"status": "accepted"})
        return body

    transport = httpx.MockTransport(handler)
    connector = OpenAPIConnector(transport=transport)

    tool_meta = {
        "method": "POST",
        "path": "/api/v1/transfers",
    }
    arguments = {
        "amount": 1000,
        "recipient": "user_999",
    }

    result = await connector.execute(
        endpoint_url="https://api.bank.internal",
        credential_ref=None,
        tool_meta=tool_meta,
        arguments=arguments,
    )

    assert result.status == "success"
    assert result.http_status == 200
    assert result.body == {"status": "accepted"}
    assert result.retryable is False


@pytest.mark.anyio
async def test_openapi_connector_4xx_client_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=404, json={"detail": "Not found"})

    transport = httpx.MockTransport(handler)
    connector = OpenAPIConnector(transport=transport)

    result = await connector.execute(
        endpoint_url="https://api.bank.internal",
        credential_ref=None,
        tool_meta={"method": "GET", "path": "/api/v1/item/{id}"},
        arguments={"id": "item_missing"},
    )

    assert result.status == "failed"
    assert result.http_status == 404
    assert result.error_code == "HTTP_404"
    assert result.retryable is False


@pytest.mark.anyio
async def test_openapi_connector_5xx_server_error_retryability():
    # GET: idempotent read -> 503 is retryable
    def handler_503(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=503, json={"detail": "Unavailable"})

    connector_get = OpenAPIConnector(transport=httpx.MockTransport(handler_503))
    result_get = await connector_get.execute(
        endpoint_url="https://api.bank.internal",
        credential_ref=None,
        tool_meta={"method": "GET", "path": "/api/v1/status"},
        arguments={},
    )
    assert result_get.status == "failed"
    assert result_get.http_status == 503
    assert result_get.retryable is True

    # POST: non-idempotent write -> 503 is NOT retryable
    connector_post = OpenAPIConnector(transport=httpx.MockTransport(handler_503))
    result_post = await connector_post.execute(
        endpoint_url="https://api.bank.internal",
        credential_ref=None,
        tool_meta={"method": "POST", "path": "/api/v1/action"},
        arguments={"x": 1},
    )
    assert result_post.status == "failed"
    assert result_post.http_status == 503
    assert result_post.retryable is False


@pytest.mark.anyio
async def test_openapi_connector_429_rate_limit():
    def handler_429(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=429, json={"detail": "Too many requests"})

    connector = OpenAPIConnector(transport=httpx.MockTransport(handler_429))
    result = await connector.execute(
        endpoint_url="https://api.bank.internal",
        credential_ref=None,
        tool_meta={"method": "GET", "path": "/api/v1/data"},
        arguments={},
    )
    assert result.status == "failed"
    assert result.http_status == 429
    assert result.retryable is True


@pytest.mark.anyio
async def test_openapi_connector_timeout():
    def handler_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Server timed out")

    connector = OpenAPIConnector(transport=httpx.MockTransport(handler_timeout))
    result = await connector.execute(
        endpoint_url="https://api.bank.internal",
        credential_ref=None,
        tool_meta={"method": "GET", "path": "/api/v1/slow"},
        arguments={},
    )
    assert result.status == "timeout"
    assert result.http_status is None
    assert result.error_code == "TOOL_EXECUTION_TIMEOUT"
    assert result.retryable is True


@pytest.mark.anyio
async def test_openapi_connector_connection_error():
    def handler_conn_err(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Failed to resolve host")

    connector = OpenAPIConnector(transport=httpx.MockTransport(handler_conn_err))
    result = await connector.execute(
        endpoint_url="https://api.bank.internal",
        credential_ref=None,
        tool_meta={"method": "GET", "path": "/api/v1/test"},
        arguments={},
    )
    assert result.status == "failed"
    assert result.http_status is None
    assert result.error_code == "TOOL_EXECUTION_FAILED"


@pytest.mark.anyio
async def test_openapi_connector_response_too_large():
    huge_bytes = b"X" * (1024 * 1024 + 100)  # > 1 MiB

    def handler_huge(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=huge_bytes,
            headers={"Content-Length": str(len(huge_bytes))},
        )

    connector = OpenAPIConnector(transport=httpx.MockTransport(handler_huge))
    result = await connector.execute(
        endpoint_url="https://api.bank.internal",
        credential_ref=None,
        tool_meta={"method": "GET", "path": "/api/v1/huge"},
        arguments={},
    )
    assert result.status == "failed"
    assert result.error_code == "TOOL_RESPONSE_TOO_LARGE"


@pytest.mark.anyio
async def test_openapi_connector_redirect_blocked():
    def handler_redirect(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=302,
            headers={"Location": "https://attacker.com/leak"},
        )

    connector = OpenAPIConnector(transport=httpx.MockTransport(handler_redirect))
    result = await connector.execute(
        endpoint_url="https://api.bank.internal",
        credential_ref=None,
        tool_meta={"method": "GET", "path": "/api/v1/redirect"},
        arguments={},
    )
    assert result.status == "failed"
    assert result.http_status == 302
    assert result.error_code == "TOOL_REDIRECT_BLOCKED"


def test_openapi_connector_path_traversal_blocked():
    connector = OpenAPIConnector()
    tool_meta = {"method": "GET", "path": "/api/v1/files/{file_id}"}

    # Attempt directory traversal with ..
    with pytest.raises(AppError) as exc_info:
        connector.validate_binding(tool_meta, {"file_id": "../../etc/passwd"})
    assert exc_info.value.code == "TOOL_ARGUMENTS_INVALID"

    # Attempt slash injection
    with pytest.raises(AppError) as exc_info:
        connector.validate_binding(tool_meta, {"file_id": "folder/subfile"})
    assert exc_info.value.code == "TOOL_ARGUMENTS_INVALID"

    # Missing required path param
    with pytest.raises(AppError) as exc_info:
        connector.validate_binding(tool_meta, {})
    assert exc_info.value.code == "TOOL_ARGUMENTS_INVALID"


@pytest.mark.anyio
async def test_openapi_connector_non_https_rejected():
    connector = OpenAPIConnector()
    with pytest.raises(AppError) as exc_info:
        await connector.execute(
            endpoint_url="http://insecure.bank.internal",
            credential_ref=None,
            tool_meta={"method": "GET", "path": "/api/v1/test"},
            arguments={},
        )
    assert exc_info.value.code == "TOOL_ENDPOINT_INVALID"


@pytest.mark.anyio
async def test_openapi_connector_non_ascii_rejected():
    connector = OpenAPIConnector()
    with pytest.raises(AppError) as exc_info:
        await connector.execute(
            endpoint_url="https://금융포털.한국",
            credential_ref=None,
            tool_meta={"method": "GET", "path": "/api/v1/test"},
            arguments={},
        )
    assert exc_info.value.code == "TOOL_ENDPOINT_INVALID"
