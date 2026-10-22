"""Financial Fixed-Length Packet connector implementation for MCP Tool Gateway.

Enforces:
- Pre-approved packet layouts with fixed byte lengths per field.
- Strict encoding handling (UTF-8, EUC-KR) and field size bounds checking.
- Packet integrity checksum verification.
- TLS-enforced TCP socket communication with 3s connection timeout.
- Non-retryable execution (side-effect safety).
"""
from __future__ import annotations

import asyncio
import hashlib
import ssl
import time
from typing import Any, Callable, Coroutine

from app.errors import AppError
from app.tools.connectors.base import BaseConnector, ConnectorResult

_MAX_PACKET_BYTES = 64 * 1024  # 64 KiB for financial packets


class FinancialPacketConnector(BaseConnector):
    """Connector for institutional legacy TCP financial packets."""

    def __init__(
        self,
        socket_factory: Callable[
            [str, int, ssl.SSLContext | None],
            Coroutine[Any, Any, tuple[asyncio.StreamReader, asyncio.StreamWriter]],
        ]
        | None = None,
    ) -> None:
        self._socket_factory = socket_factory

    def validate_binding(
        self,
        tool_meta: dict[str, Any],
        arguments: dict[str, Any],
    ) -> None:
        """Validate layout definitions, fields, and argument length limits."""
        layout_version = tool_meta.get("layout_version")
        if not layout_version or not isinstance(layout_version, str):
            raise AppError("TOOL_ARGUMENTS_INVALID", 400)

        fields = tool_meta.get("fields")
        if not fields or not isinstance(fields, list):
            raise AppError("TOOL_ARGUMENTS_INVALID", 400)

        encoding = tool_meta.get("encoding", "utf-8").lower()
        if encoding not in {"utf-8", "euc-kr", "cp949"}:
            raise AppError("TOOL_ARGUMENTS_INVALID", 400)

        for field in fields:
            name = field.get("name")
            length = field.get("length")
            if not name or not isinstance(length, int) or length <= 0:
                raise AppError("TOOL_ARGUMENTS_INVALID", 400)

            if field.get("required", False) and name not in arguments:
                raise AppError("TOOL_ARGUMENTS_INVALID", 400)

            if name in arguments:
                val = str(arguments[name])
                encoded_len = len(val.encode(encoding))
                if encoded_len > length:
                    raise AppError("TOOL_ARGUMENTS_INVALID", 400)

    @staticmethod
    def _compute_lrc(data: bytes) -> int:
        """Calculate Longitudinal Redundancy Check (LRC) byte."""
        lrc = 0
        for b in data:
            lrc ^= b
        return lrc

    def _pack(
        self,
        fields: list[dict[str, Any]],
        arguments: dict[str, Any],
        encoding: str,
    ) -> bytes:
        """Pack arguments into fixed-length byte buffer with 1-byte LRC trailer."""
        packet_buf = bytearray()
        for field in fields:
            name = field["name"]
            length = field["length"]
            field_type = field.get("type", "str")
            val = arguments.get(name, "")

            if field_type == "int":
                # Right-aligned zero-padded
                s = str(val).zfill(length)
                raw_field = s.encode("ascii")
            else:
                # Left-aligned space-padded
                raw_val = str(val).encode(encoding)
                padding = b" " * (length - len(raw_val))
                raw_field = raw_val + padding

            packet_buf.extend(raw_field)

        # Append LRC checksum byte
        lrc = self._compute_lrc(packet_buf)
        packet_buf.append(lrc)
        return bytes(packet_buf)

    def _unpack(
        self,
        response_fields: list[dict[str, Any]],
        data: bytes,
        encoding: str,
    ) -> dict[str, Any]:
        """Unpack response bytes according to layout and verify LRC."""
        if not data:
            return {}

        # Verify LRC byte at end
        body_data = data[:-1]
        received_lrc = data[-1]
        expected_lrc = self._compute_lrc(body_data)
        if received_lrc != expected_lrc:
            raise AppError("TOOL_INPUT_BLOCKED", 400)

        result: dict[str, Any] = {}
        offset = 0
        for field in response_fields:
            name = field["name"]
            length = field["length"]
            field_type = field.get("type", "str")

            chunk = body_data[offset : offset + length]
            offset += length

            decoded = chunk.decode(encoding, errors="replace").strip()
            if field_type == "int":
                result[name] = int(decoded) if decoded.isdigit() else 0
            else:
                result[name] = decoded

        return result

    async def execute(
        self,
        endpoint_url: str,
        credential_ref: str | None,
        tool_meta: dict[str, Any],
        arguments: dict[str, Any],
        timeout_seconds: int = 10,
    ) -> ConnectorResult:
        """Connect over TCP/TLS, send fixed packet, and unpack response."""
        self.validate_binding(tool_meta, arguments)

        fields = tool_meta["fields"]
        response_fields = tool_meta.get("response_fields", fields)
        encoding = tool_meta.get("encoding", "utf-8").lower()

        # Parse endpoint: tls://host:port or tcp://host:port
        host, _, port_str = endpoint_url.replace("tls://", "").replace("tcp://", "").partition(":")
        port = int(port_str) if port_str else 9443

        packet_bytes = self._pack(fields, arguments, encoding)
        if len(packet_bytes) > _MAX_PACKET_BYTES:
            raise AppError("TOOL_ARGUMENTS_INVALID", 400)

        start_time = time.perf_counter()
        reader: asyncio.StreamReader | None = None
        writer: asyncio.StreamWriter | None = None

        try:
            if self._socket_factory:
                reader, writer = await asyncio.wait_for(
                    self._socket_factory(host, port, None),
                    timeout=3.0,
                )
            else:
                ssl_ctx = ssl.create_default_context()
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port, ssl=ssl_ctx),
                    timeout=3.0,
                )

            writer.write(packet_bytes)
            await writer.drain()

            expected_resp_len = sum(f["length"] for f in response_fields) + 1  # +1 for LRC
            resp_data = await asyncio.wait_for(
                reader.readexactly(expected_resp_len),
                timeout=float(timeout_seconds),
            )

            duration_ms = int((time.perf_counter() - start_time) * 1000)
            digest = hashlib.sha256(resp_data).hexdigest()

            unpacked_body = self._unpack(response_fields, resp_data, encoding)

            return ConnectorResult(
                status="success",
                http_status=200,
                body=unpacked_body,
                duration_ms=duration_ms,
                error_code=None,
                redacted_digest=digest,
                retryable=False,
            )

        except asyncio.TimeoutError:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return ConnectorResult(
                status="timeout",
                http_status=None,
                body={"error": "Financial socket communication timed out"},
                duration_ms=duration_ms,
                error_code="TOOL_EXECUTION_TIMEOUT",
                redacted_digest=hashlib.sha256(b"").hexdigest(),
                retryable=False,
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return ConnectorResult(
                status="failed",
                http_status=None,
                body={"error": f"Financial socket error: {type(exc).__name__}"},
                duration_ms=duration_ms,
                error_code="TOOL_EXECUTION_FAILED",
                redacted_digest=hashlib.sha256(b"").hexdigest(),
                retryable=False,
            )
        finally:
            if writer:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass
