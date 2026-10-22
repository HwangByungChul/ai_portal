"""Contract tests for WSDLConnector using httpx.MockTransport."""
import pytest
import httpx

from app.errors import AppError
from app.tools.connectors.wsdl_connector import WSDLConnector


@pytest.mark.anyio
async def test_wsdl_connector_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.headers["SOAPAction"] == '"InquireBalance"'
        response_xml = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            '<soap:Body>'
            '<InquireBalanceResponse>'
            '<account_number>123-456</account_number>'
            '<balance>350000</balance>'
            '</InquireBalanceResponse>'
            '</soap:Body>'
            '</soap:Envelope>'
        )
        return httpx.Response(200, content=response_xml.encode("utf-8"), headers={"Content-Type": "text/xml"})

    connector = WSDLConnector(transport=httpx.MockTransport(handler))
    tool_meta = {
        "operation": "InquireBalance",
        "soap_action": "InquireBalance",
        "allowed_actions": ["InquireBalance"],
    }
    arguments = {"account_number": "123-456"}

    result = await connector.execute(
        endpoint_url="https://soap.bank.internal/ws",
        credential_ref="mock_token",
        tool_meta=tool_meta,
        arguments=arguments,
    )

    assert result.status == "success"
    assert result.http_status == 200
    assert result.body["account_number"] == "123-456"
    assert result.body["balance"] == "350000"
    assert result.retryable is False


def test_wsdl_connector_unsupported_features():
    connector = WSDLConnector()
    with pytest.raises(AppError) as exc_info:
        connector.validate_binding(
            {"operation": "Op", "soap_action": "Act", "ws_security": True},
            {},
        )
    assert exc_info.value.code == "FEATURE_NOT_READY"


def test_wsdl_connector_action_blocked():
    connector = WSDLConnector()
    with pytest.raises(AppError) as exc_info:
        connector.validate_binding(
            {"operation": "Op", "soap_action": "UnapprovedAction", "allowed_actions": ["ApprovedAction"]},
            {},
        )
    assert exc_info.value.code == "TOOL_INPUT_BLOCKED"
