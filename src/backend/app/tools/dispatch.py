"""Connector Dispatcher for MCP Tool Gateway.

Enforces:
- Pre-dispatch Rate Limiting and Circuit Breaker state verification.
- Concurrency limiting via asyncio.Semaphore per tool.
- Non-repudiation audit logging for invocation start, success results, and failure events.
- Strict dispatch routing to typed connectors (OpenAPI, WSDL, JDBC, Financial Packet).
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Literal
from uuid import uuid4

from app.errors import AppError
from app.tools.audit import AuditLedgerService
from app.tools.connectors.base import BaseConnector, ConnectorResult
from app.tools.connectors.financial_packet_connector import FinancialPacketConnector
from app.tools.connectors.jdbc_connector import JDBCConnector
from app.tools.connectors.openapi_connector import OpenAPIConnector
from app.tools.connectors.wsdl_connector import WSDLConnector
from app.tools.resilience import CircuitBreaker, ConcurrencyLimiter, TokenBucketRateLimiter


class ConnectorDispatcher:
    """Orchestrates resilient, audited execution of typed connectors."""

    def __init__(
        self,
        rate_limiter: TokenBucketRateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        concurrency_limiter: ConcurrencyLimiter | None = None,
        audit_service: AuditLedgerService | None = None,
        connectors: dict[str, BaseConnector] | None = None,
    ) -> None:
        self.rate_limiter = rate_limiter or TokenBucketRateLimiter()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.concurrency_limiter = concurrency_limiter or ConcurrencyLimiter()
        self.audit_service = audit_service or AuditLedgerService()

        # Default connectors mapping
        self.connectors = connectors or {
            "openapi": OpenAPIConnector(),
            "wsdl": WSDLConnector(),
            "jdbc": JDBCConnector(),
            "financial_packet": FinancialPacketConnector(),
        }

    async def dispatch(
        self,
        tenant_id: str,
        actor_id: str,
        trace_id: str,
        tool_id: str,
        source_type: str,
        endpoint_url: str,
        credential_ref: str | None,
        tool_meta: dict[str, Any],
        arguments: dict[str, Any],
        *,
        timeout_seconds: int = 10,
        rate_limit_per_minute: int | None = None,
    ) -> ConnectorResult:
        """Execute a tool invocation with full resilience and audit gates."""
        arg_json = json.dumps(arguments, sort_keys=True, default=str)
        arg_digest = hashlib.sha256(arg_json.encode("utf-8")).hexdigest()

        # 1. Rate Limiting Check
        tokens = rate_limit_per_minute or 60
        refill_rate = tokens / 60.0
        if not self.rate_limiter.try_acquire(tenant_id, tool_id, max_tokens=tokens, refill_rate=refill_rate):
            await self.audit_service.append(
                tenant_id=tenant_id,
                actor_id=actor_id,
                trace_id=trace_id,
                tool_id=tool_id,
                event_type="rate_limit",
                argument_digest=arg_digest,
                status="blocked",
                error_code="TOOL_RATE_LIMITED",
            )
            raise AppError("TOOL_RATE_LIMITED", 429)

        # 2. Circuit Breaker Check
        if not self.circuit_breaker.can_execute(tenant_id, tool_id):
            await self.audit_service.append(
                tenant_id=tenant_id,
                actor_id=actor_id,
                trace_id=trace_id,
                tool_id=tool_id,
                event_type="circuit_open",
                argument_digest=arg_digest,
                status="blocked",
                error_code="TOOL_CIRCUIT_OPEN",
            )
            raise AppError("TOOL_CIRCUIT_OPEN", 503)

        # 3. Locate connector
        connector = self.connectors.get(source_type)
        if not connector:
            raise AppError("TOOL_ARGUMENTS_INVALID", 400)

        # 4. Record invocation start
        await self.audit_service.append(
            tenant_id=tenant_id,
            actor_id=actor_id,
            trace_id=trace_id,
            tool_id=tool_id,
            event_type="invocation",
            credential_ref_id=credential_ref,
            argument_digest=arg_digest,
            status="success",
        )

        # 5. Acquire Concurrency Semaphore and Execute
        sem = self.concurrency_limiter.get_semaphore(tool_id)
        start_time = time.perf_counter()

        async with sem:
            result = await connector.execute(
                endpoint_url=endpoint_url,
                credential_ref=credential_ref,
                tool_meta=tool_meta,
                arguments=arguments,
                timeout_seconds=timeout_seconds,
            )

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        # 6. Record Outcome & Update Circuit Breaker
        if result.status == "success":
            self.circuit_breaker.record_success(tenant_id, tool_id)
            await self.audit_service.append(
                tenant_id=tenant_id,
                actor_id=actor_id,
                trace_id=trace_id,
                tool_id=tool_id,
                event_type="result",
                argument_digest=arg_digest,
                response_digest=result.redacted_digest,
                duration_ms=duration_ms,
                status="success",
            )
        else:
            self.circuit_breaker.record_failure(tenant_id, tool_id)
            await self.audit_service.append(
                tenant_id=tenant_id,
                actor_id=actor_id,
                trace_id=trace_id,
                tool_id=tool_id,
                event_type="error",
                argument_digest=arg_digest,
                response_digest=result.redacted_digest,
                duration_ms=duration_ms,
                status=result.status,
                error_code=result.error_code,
            )

        return result
