"""JDBC / Database View Connector implementation for MCP Tool Gateway.

Enforces:
- Strict read-only query semantics via psycopg (readonly=True, immediate rollback).
- Whitelisted database views only; raw string-concatenated SQL queries strictly prohibited.
- Single-shot transaction without connection pooling for strict tenant/caller isolation.
- Structured parameter binding using psycopg %s format.
- Non-retryable execution (side-effect safety).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Callable

from app.errors import AppError
from app.tools.connectors.base import BaseConnector, ConnectorResult

_VIEW_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")
_DANGEROUS_SQL_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)
_MAX_RESULT_ROWS = 500


class JDBCConnector(BaseConnector):
    """Connector for querying pre-approved read-only database views."""

    def __init__(
        self,
        executor_func: Callable[[str, list[Any]], list[dict[str, Any]]] | None = None,
    ) -> None:
        """Initialize JDBCConnector with an optional synchronous/async query executor hook for tests."""
        self._executor_func = executor_func

    def validate_binding(
        self,
        tool_meta: dict[str, Any],
        arguments: dict[str, Any],
    ) -> None:
        """Validate view name, whitelisted columns, and absence of DDL/DML injection."""
        view_name = tool_meta.get("view_name")
        if not view_name or not isinstance(view_name, str):
            raise AppError("TOOL_ARGUMENTS_INVALID", 400)

        if not _VIEW_NAME_PATTERN.match(view_name):
            raise AppError("TOOL_ARGUMENTS_INVALID", 400)

        if _DANGEROUS_SQL_PATTERN.search(view_name):
            raise AppError("TOOL_INPUT_BLOCKED", 400)

        # Check allowed parameter columns
        allowed_columns = tool_meta.get("allowed_columns")
        if allowed_columns is not None:
            for k in arguments.keys():
                if k not in allowed_columns:
                    raise AppError("TOOL_ARGUMENTS_INVALID", 400)

        for k, v in arguments.items():
            if not _VIEW_NAME_PATTERN.match(str(k)):
                raise AppError("TOOL_ARGUMENTS_INVALID", 400)
            if isinstance(v, str) and _DANGEROUS_SQL_PATTERN.search(v):
                raise AppError("TOOL_INPUT_BLOCKED", 400)

    async def execute(
        self,
        endpoint_url: str,
        credential_ref: str | None,
        tool_meta: dict[str, Any],
        arguments: dict[str, Any],
        timeout_seconds: int = 10,
    ) -> ConnectorResult:
        """Execute parameterized read-only view query."""
        self.validate_binding(tool_meta, arguments)

        view_name = str(tool_meta["view_name"])
        start_time = time.perf_counter()

        # Build parameterized query: SELECT * FROM view_name WHERE col1 = %s AND col2 = %s
        where_clauses = []
        bind_params = []
        for col, val in sorted(arguments.items()):
            where_clauses.append(f"{col} = %s")
            bind_params.append(val)

        where_stmt = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        query = f"SELECT * FROM {view_name}{where_stmt} LIMIT {_MAX_RESULT_ROWS + 1}"

        try:
            if self._executor_func:
                rows = self._executor_func(query, bind_params)
            else:
                # Default read-only psycopg execution using endpoint_url (conninfo)
                import psycopg
                rows = []
                with psycopg.connect(endpoint_url, autocommit=False) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SET TRANSACTION READ ONLY;")
                        cur.execute(query, bind_params)
                        cols = [desc[0] for desc in cur.description] if cur.description else []
                        for r in cur.fetchall():
                            rows.append(dict(zip(cols, r)))
                        conn.rollback()

            duration_ms = int((time.perf_counter() - start_time) * 1000)

            if len(rows) > _MAX_RESULT_ROWS:
                return ConnectorResult(
                    status="failed",
                    http_status=None,
                    body={"error": f"Result exceeds maximum allowed rows ({_MAX_RESULT_ROWS})"},
                    duration_ms=duration_ms,
                    error_code="TOOL_RESPONSE_TOO_LARGE",
                    redacted_digest=hashlib.sha256(b"").hexdigest(),
                    retryable=False,
                )

            body_dict = {"rows": rows, "count": len(rows)}
            body_bytes = json.dumps(body_dict, default=str, sort_keys=True).encode("utf-8")
            digest = hashlib.sha256(body_bytes).hexdigest()

            return ConnectorResult(
                status="success",
                http_status=200,
                body=body_dict,
                duration_ms=duration_ms,
                error_code=None,
                redacted_digest=digest,
                retryable=False,
            )

        except Exception as exc:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return ConnectorResult(
                status="failed",
                http_status=None,
                body={"error": f"JDBC query error: {type(exc).__name__}"},
                duration_ms=duration_ms,
                error_code="TOOL_EXECUTION_FAILED",
                redacted_digest=hashlib.sha256(b"").hexdigest(),
                retryable=False,
            )
