"""Base Connector interface and data transfer objects for MCP Tool Gateway.

Enforces:
- Common Connector contract across OpenAPI, WSDL, JDBC, and Financial Packet.
- Standardized execution result with timing, digest, error code, and retryability.
- Strict input and binding validation before network dispatch.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class ConnectorResult:
    """Standardized connector execution result.

    Never stores full raw external response bodies in persistent logs.
    """
    status: Literal["success", "failed", "unknown", "timeout"]
    http_status: int | None
    body: dict[str, Any] | None
    duration_ms: int
    error_code: str | None
    redacted_digest: str
    retryable: bool


class BaseConnector(ABC):
    """Abstract base class for all institutional and external connectors."""

    @abstractmethod
    async def execute(
        self,
        endpoint_url: str,
        credential_ref: str | None,
        tool_meta: dict[str, Any],
        arguments: dict[str, Any],
        timeout_seconds: int,
    ) -> ConnectorResult:
        """Execute a tool invocation against the target endpoint."""
        ...

    @abstractmethod
    def validate_binding(
        self,
        tool_meta: dict[str, Any],
        arguments: dict[str, Any],
    ) -> None:
        """Validate that arguments conform to the tool metadata binding requirements."""
        ...
