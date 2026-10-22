"""OpenAPI/REST connector implementation for MCP Tool Gateway.

Enforces:
- HTTPS only with redirect prohibition (follow_redirects=False).
- Strict path parameter isolation and regex whitelisting to block path traversal.
- Identity content-encoding with 1 MiB maximum response body limit.
- Redacted SHA-256 digest recording; raw payload never stored in persistent audit.
- Idempotent GET/HEAD retryability assessment on transient failures.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
from typing import Any

import httpx

from app.errors import AppError
from app.tools.connectors.base import BaseConnector, ConnectorResult

_MAX_RESPONSE_BYTES = 1024 * 1024  # 1 MiB
_ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"}
_PATH_PARAM_PATTERN = re.compile(r"\{([a-zA-Z0-9_]+)\}")
_SAFE_PARAM_VALUE = re.compile(r"^[a-zA-Z0-9_.-]+$")


class OpenAPIConnector(BaseConnector):
    """Connector for standard RESTful OpenAPI endpoints."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    def validate_binding(
        self,
        tool_meta: dict[str, Any],
        arguments: dict[str, Any],
    ) -> None:
        """Validate path, method, and path parameter argument bindings."""
        method = str(tool_meta.get("method", "")).upper()
        if not method or method not in _ALLOWED_METHODS:
            raise AppError("TOOL_ARGUMENTS_INVALID", 400)

        path = str(tool_meta.get("path", ""))
        if not path:
            raise AppError("TOOL_ARGUMENTS_INVALID", 400)

        params_in_path = _PATH_PARAM_PATTERN.findall(path)
        for param in params_in_path:
            if param not in arguments:
                raise AppError("TOOL_ARGUMENTS_INVALID", 400)
            val = str(arguments[param])
            if not _SAFE_PARAM_VALUE.match(val):
                raise AppError("TOOL_ARGUMENTS_INVALID", 400)
            if ".." in val or "/" in val or "\\" in val:
                raise AppError("TOOL_ARGUMENTS_INVALID", 400)

    @staticmethod
    def _validate_endpoint(endpoint_url: str) -> urllib.parse.ParseResult:
        if not endpoint_url:
            raise AppError("TOOL_ENDPOINT_INVALID", 400)

        try:
            endpoint_url.encode("ascii")
        except UnicodeEncodeError:
            raise AppError("TOOL_ENDPOINT_INVALID", 400)

        parsed = urllib.parse.urlparse(endpoint_url)
        if parsed.scheme.lower() != "https":
            raise AppError("TOOL_ENDPOINT_INVALID", 400)
        if not parsed.netloc:
            raise AppError("TOOL_ENDPOINT_INVALID", 400)

        return parsed

    async def execute(
        self,
        endpoint_url: str,
        credential_ref: str | None,
        tool_meta: dict[str, Any],
        arguments: dict[str, Any],
        timeout_seconds: int = 10,
    ) -> ConnectorResult:
        """Execute OpenAPI HTTP request and return normalized ConnectorResult."""
        self.validate_binding(tool_meta, arguments)
        parsed_base = self._validate_endpoint(endpoint_url)

        method = str(tool_meta.get("method", "GET")).upper()
        raw_path = str(tool_meta.get("path", ""))

        # Replace path parameters
        resolved_path = raw_path
        used_keys = set()
        for param in _PATH_PARAM_PATTERN.findall(raw_path):
            resolved_path = resolved_path.replace(f"{{{param}}}", str(arguments[param]))
            used_keys.add(param)

        remaining_args = {k: v for k, v in arguments.items() if k not in used_keys}

        # Combine base URL path and resolved path
        base_path = parsed_base.path.rstrip("/")
        normalized_subpath = resolved_path if resolved_path.startswith("/") else f"/{resolved_path}"
        full_path = f"{base_path}{normalized_subpath}"
        target_url = urllib.parse.urlunparse(
            (parsed_base.scheme, parsed_base.netloc, full_path, "", "", "")
        )

        headers: dict[str, str] = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": "AI-Platform-OpenAPIConnector/1.0",
        }
        if credential_ref:
            headers["Authorization"] = f"Bearer {credential_ref}"

        params: dict[str, Any] | None = None
        json_body: Any = None

        if method in {"GET", "HEAD", "DELETE"}:
            params = remaining_args or None
        else:
            headers["Content-Type"] = "application/json"
            json_body = remaining_args

        is_idempotent = method in {"GET", "HEAD"}
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
                response = await client.request(
                    method=method,
                    url=target_url,
                    params=params,
                    json=json_body,
                    headers=headers,
                )

                duration_ms = int((time.perf_counter() - start_time) * 1000)

                # Check redirect prohibition
                if 300 <= response.status_code < 400:
                    raw_content = response.content
                    digest = hashlib.sha256(raw_content).hexdigest()
                    return ConnectorResult(
                        status="failed",
                        http_status=response.status_code,
                        body={"error": "Redirect blocked by security policy"},
                        duration_ms=duration_ms,
                        error_code="TOOL_REDIRECT_BLOCKED",
                        redacted_digest=digest,
                        retryable=False,
                    )

                # Check response payload limit
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > _MAX_RESPONSE_BYTES:
                    return ConnectorResult(
                        status="failed",
                        http_status=response.status_code,
                        body={"error": "Response exceeds maximum allowed size (1 MiB)"},
                        duration_ms=duration_ms,
                        error_code="TOOL_RESPONSE_TOO_LARGE",
                        redacted_digest=hashlib.sha256(b"").hexdigest(),
                        retryable=False,
                    )

                raw_content = response.content
                if len(raw_content) > _MAX_RESPONSE_BYTES:
                    return ConnectorResult(
                        status="failed",
                        http_status=response.status_code,
                        body={"error": "Response exceeds maximum allowed size (1 MiB)"},
                        duration_ms=duration_ms,
                        error_code="TOOL_RESPONSE_TOO_LARGE",
                        redacted_digest=hashlib.sha256(b"").hexdigest(),
                        retryable=False,
                    )

                digest = hashlib.sha256(raw_content).hexdigest()

                try:
                    parsed_body = response.json()
                    if not isinstance(parsed_body, dict):
                        parsed_body = {"data": parsed_body}
                except Exception:
                    text_preview = response.text[:500] if response.text else ""
                    parsed_body = {"raw_text": text_preview}

                if 200 <= response.status_code < 300:
                    return ConnectorResult(
                        status="success",
                        http_status=response.status_code,
                        body=parsed_body,
                        duration_ms=duration_ms,
                        error_code=None,
                        redacted_digest=digest,
                        retryable=False,
                    )

                # 4xx or 5xx
                retryable = is_idempotent and (response.status_code in {429, 502, 503, 504})
                return ConnectorResult(
                    status="failed",
                    http_status=response.status_code,
                    body=parsed_body,
                    duration_ms=duration_ms,
                    error_code=f"HTTP_{response.status_code}",
                    redacted_digest=digest,
                    retryable=retryable,
                )

        except httpx.TimeoutException:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return ConnectorResult(
                status="timeout",
                http_status=None,
                body={"error": "Tool execution timed out"},
                duration_ms=duration_ms,
                error_code="TOOL_EXECUTION_TIMEOUT",
                redacted_digest=hashlib.sha256(b"").hexdigest(),
                retryable=is_idempotent,
            )
        except (httpx.ConnectError, httpx.RequestError) as exc:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return ConnectorResult(
                status="failed",
                http_status=None,
                body={"error": f"Tool network communication error: {type(exc).__name__}"},
                duration_ms=duration_ms,
                error_code="TOOL_EXECUTION_FAILED",
                redacted_digest=hashlib.sha256(b"").hexdigest(),
                retryable=is_idempotent,
            )
