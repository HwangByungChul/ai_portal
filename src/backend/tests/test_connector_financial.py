"""Contract tests for FinancialPacketConnector."""
import asyncio
import pytest

from app.errors import AppError
from app.tools.connectors.financial_packet_connector import FinancialPacketConnector


@pytest.mark.anyio
async def test_financial_connector_success():
    fields = [
        {"name": "tx_code", "length": 4, "type": "str"},
        {"name": "account", "length": 10, "type": "str"},
        {"name": "amount", "length": 8, "type": "int"},
    ]
    response_fields = [
        {"name": "res_code", "length": 2, "type": "str"},
        {"name": "balance", "length": 8, "type": "int"},
    ]

    # Pre-calculated response: "00" + "00050000" (total 10 bytes) + LRC byte
    resp_payload = b"0000050000"
    lrc = FinancialPacketConnector._compute_lrc(resp_payload)
    mock_resp_bytes = resp_payload + bytes([lrc])

    async def mock_socket_factory(host: str, port: int, ssl_ctx):
        reader = asyncio.StreamReader()
        reader.feed_data(mock_resp_bytes)
        reader.feed_eof()

        class MockWriter:
            def __init__(self):
                self.written = b""

            def write(self, data):
                self.written += data

            async def drain(self):
                pass

            def close(self):
                pass

            async def wait_closed(self):
                pass

        return reader, MockWriter()

    connector = FinancialPacketConnector(socket_factory=mock_socket_factory)
    tool_meta = {
        "layout_version": "FIN_V1",
        "fields": fields,
        "response_fields": response_fields,
        "encoding": "utf-8",
    }
    arguments = {
        "tx_code": "INQ1",
        "account": "1234567890",
        "amount": 500,
    }

    result = await connector.execute(
        endpoint_url="tls://corebank.internal:9443",
        credential_ref=None,
        tool_meta=tool_meta,
        arguments=arguments,
    )

    assert result.status == "success"
    assert result.http_status == 200
    assert result.body["res_code"] == "00"
    assert result.body["balance"] == 50000
    assert result.retryable is False


def test_financial_connector_field_length_overflow():
    connector = FinancialPacketConnector()
    tool_meta = {
        "layout_version": "FIN_V1",
        "fields": [{"name": "tx_code", "length": 4, "type": "str"}],
    }
    # 5 chars > 4 allowed length
    with pytest.raises(AppError) as exc_info:
        connector.validate_binding(tool_meta, {"tx_code": "TOOLONG"})
    assert exc_info.value.code == "TOOL_ARGUMENTS_INVALID"
