"""SOAP/WSDL connector implementation for MCP Tool Gateway.

Enforces:
- SOAP 1.1 and 1.2 envelope construction over HTTPS.
- XML external entity (XXE) and DTD injection prevention via defusedxml.
- Strict SOAP Action allowlisting against tool_meta.
- Explicit non-support rejection for WS-Security, MTOM, and complex WSDL imports.
- Non-retryable execution (side-effect safety).
"""
from __future__ import annotations

import hashlib
import time
import urllib.parse
from typing import Any

from xml.sax.saxutils import escape as xml_escape

import defusedxml.ElementTree as ET
import httpx

from app.errors import AppError
from app.tools.connectors.base import BaseConnector, ConnectorResult

_MAX_RESPONSE_BYTES = 1024 * 1024  # 1 MiB


class WSDLConnector(BaseConnector):
    """Connector for institutional SOAP/XML web services."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    def validate_binding(
        self,
        tool_meta: dict[str, Any],
        arguments: dict[str, Any],
    ) -> None:
        """Validate SOAP action, operation, and security boundary."""
        if tool_meta.get("ws_security") or tool_meta.get("mtom") or tool_meta.get("complex_imports"):
            raise AppError("FEATURE_NOT_READY", 409)

        operation = tool_meta.get("operation")
        if not operation or not isinstance(operation, str):
            raise AppError("TOOL_ARGUMENTS_INVALID", 400)

        soap_action = tool_meta.get("soap_action")
        if not soap_action or not isinstance(soap_action, str):
            raise AppError("TOOL_ARGUMENTS_INVALID", 400)

        allowed_actions = tool_meta.get("allowed_actions")
        if allowed_actions is not None and soap_action not in allowed_actions:
            raise AppError("TOOL_INPUT_BLOCKED", 400)

    @staticmethod
    def _validate_endpoint(endpoint_url: str) -> urllib.parse.ParseResult:
        if not endpoint_url:
            raise AppError("TOOL_ENDPOINT_INVALID", 400)
        parsed = urllib.parse.urlparse(endpoint_url)
        if parsed.scheme.lower() != "https" or not parsed.netloc:
            raise AppError("TOOL_ENDPOINT_INVALID", 400)
        return parsed

    @staticmethod
    def _build_soap_envelope(operation: str, arguments: dict[str, Any], version: str = "1.1") -> tuple[str, str]:
        # Escape XML special chars in values
        arg_xml_parts = []
        for k, v in arguments.items():
            safe_k = xml_escape(str(k))
            safe_v = xml_escape(str(v))
            arg_xml_parts.append(f"<{safe_k}>{safe_v}</{safe_k}>")
        body_content = "".join(arg_xml_parts)

        if version == "1.2":
            content_type = "application/soap+xml; charset=utf-8"
            envelope = (
                '<?xml version="1.0" encoding="utf-8"?>'
                '<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
                'xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
                f"<soap12:Body><{operation}>{body_content}</{operation}></soap12:Body>"
                "</soap12:Envelope>"
            )
        else:
            content_type = 'text/xml; charset=utf-8'
            envelope = (
                '<?xml version="1.0" encoding="utf-8"?>'
                '<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
                'xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
                f"<soap:Body><{operation}>{body_content}</{operation}></soap:Body>"
                "</soap:Envelope>"
            )
        return envelope, content_type

    @staticmethod
    def _parse_soap_response(xml_bytes: bytes) -> dict[str, Any]:
        """Safely parse SOAP response into a flattened dict using defusedxml."""
        root = ET.fromstring(xml_bytes)
        result: dict[str, Any] = {}
        # Traverse elements and extract text
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if elem.text and elem.text.strip():
                result[tag] = elem.text.strip()
        return result

    async def execute(
        self,
        endpoint_url: str,
        credential_ref: str | None,
        tool_meta: dict[str, Any],
        arguments: dict[str, Any],
        timeout_seconds: int = 10,
    ) -> ConnectorResult:
        """Execute SOAP request over HTTPS with defusedxml parsing."""
        self.validate_binding(tool_meta, arguments)
        self._validate_endpoint(endpoint_url)

        operation = str(tool_meta["operation"])
        soap_action = str(tool_meta["soap_action"])
        version = str(tool_meta.get("soap_version", "1.1"))

        envelope_xml, content_type = self._build_soap_envelope(operation, arguments, version)

        headers: dict[str, str] = {
            "Content-Type": content_type,
            "SOAPAction": f'"{soap_action}"',
            "Accept-Encoding": "identity",
            "User-Agent": "AI-Platform-WSDLConnector/1.0",
        }
        if credential_ref:
            headers["Authorization"] = f"Bearer {credential_ref}"

        timeout = httpx.Timeout(
            connect=5.0,
            read=float(timeout_seconds),
            write=5.0,
            pool=5.0,
        )

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                follow_redirects=False,
                timeout=timeout,
            ) as client:
                response = await client.post(
                    url=endpoint_url,
                    content=envelope_xml.encode("utf-8"),
                    headers=headers,
                )

                duration_ms = int((time.perf_counter() - start_time) * 1000)

                if 300 <= response.status_code < 400:
                    digest = hashlib.sha256(response.content).hexdigest()
                    return ConnectorResult(
                        status="failed",
                        http_status=response.status_code,
                        body={"error": "Redirect prohibited"},
                        duration_ms=duration_ms,
                        error_code="TOOL_REDIRECT_BLOCKED",
                        redacted_digest=digest,
                        retryable=False,
                    )

                if len(response.content) > _MAX_RESPONSE_BYTES:
                    return ConnectorResult(
                        status="failed",
                        http_status=response.status_code,
                        body={"error": "Response exceeds 1 MiB"},
                        duration_ms=duration_ms,
                        error_code="TOOL_RESPONSE_TOO_LARGE",
                        redacted_digest=hashlib.sha256(b"").hexdigest(),
                        retryable=False,
                    )

                raw_bytes = response.content
                digest = hashlib.sha256(raw_bytes).hexdigest()

                try:
                    parsed_dict = self._parse_soap_response(raw_bytes)
                except Exception as parse_err:
                    parsed_dict = {"parse_error": str(parse_err)}

                if 200 <= response.status_code < 300:
                    return ConnectorResult(
                        status="success",
                        http_status=response.status_code,
                        body=parsed_dict,
                        duration_ms=duration_ms,
                        error_code=None,
                        redacted_digest=digest,
                        retryable=False,
                    )

                return ConnectorResult(
                    status="failed",
                    http_status=response.status_code,
                    body=parsed_dict,
                    duration_ms=duration_ms,
                    error_code=f"SOAP_{response.status_code}",
                    redacted_digest=digest,
                    retryable=False,
                )

        except httpx.TimeoutException:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return ConnectorResult(
                status="timeout",
                http_status=None,
                body={"error": "SOAP service timed out"},
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
                body={"error": f"SOAP communication error: {type(exc).__name__}"},
                duration_ms=duration_ms,
                error_code="TOOL_EXECUTION_FAILED",
                redacted_digest=hashlib.sha256(b"").hexdigest(),
                retryable=False,
            )
