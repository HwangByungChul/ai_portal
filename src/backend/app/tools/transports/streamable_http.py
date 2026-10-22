"""Read-only MCP discovery. Host policy is not a complete SSRF defense.

No application retries; official SDK negotiation/reconnection remains enabled.
No credentials, proxy environment, shared session cache, or app route is accepted.
"""
from dataclasses import dataclass, field
from importlib.metadata import version
import json
import re
from urllib.parse import urlsplit

import anyio
import httpx
from jsonschema import Draft202012Validator
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

MAX_CATALOG_ENTRIES = 100
MAX_PAGES = 100
MAX_SSE_EVENT_BYTES = 262144
# 2 MiB accommodates 100 small schemas plus negotiation within the 20s deadline.
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DISCOVERY_TIMEOUT_SECONDS = 20
_NAME = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
_HOST = re.compile(r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\Z")


class DiscoveryError(ValueError):
    """Fixed public error; never includes transport or response details."""


class _ResponseRejected(Exception):
    """Internal fixed failure; never carry response data into SDK errors."""


@dataclass
class _ResponseBudget:
    """Shared by every response in one discovery call, including negotiation."""

    consumed: int = 0
    rejected: bool = False


class _BudgetStream(httpx.AsyncByteStream):
    def __init__(self, stream: httpx.AsyncByteStream, budget: _ResponseBudget):
        self._stream, self._budget = stream, budget
        self._closed = False

    async def __aiter__(self):
        async for chunk in self._stream:
            self._budget.consumed += len(chunk)
            if self._budget.rejected or self._budget.consumed > MAX_RESPONSE_BYTES:
                self._budget.rejected = True
                await self.aclose()
                raise _ResponseRejected()
            yield chunk

    async def aclose(self) -> None:
        if not self._closed:
            self._closed = True
            # Cleanup must complete even when the SDK task group is cancelling.
            with anyio.CancelScope(shield=True):
                await self._stream.aclose()


class _BudgetTransport(httpx.AsyncBaseTransport):
    def __init__(self, transport: httpx.AsyncBaseTransport):
        self._transport = transport
        self._budget = _ResponseBudget()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self._budget.rejected:
            raise _ResponseRejected()
        response = await self._transport.handle_async_request(request)
        stream = _BudgetStream(response.stream, self._budget)
        # Identity makes the raw byte cap also bound the body passed to parsers.
        if response.headers.get("content-encoding", "identity").strip().lower() != "identity":
            self._budget.rejected = True
            await stream.aclose()
            raise _ResponseRejected()
        # Rebuild with public transport fields so pre-buffered MockTransport
        # responses take the same counted streaming path as network responses.
        return httpx.Response(response.status_code, headers=response.headers,
                              stream=stream, extensions=response.extensions)

    async def aclose(self) -> None:
        await self._transport.aclose()


@dataclass(frozen=True)
class EndpointConfig:
    url: str = field(repr=False)
    allowed_hosts: frozenset[str]

    def __post_init__(self) -> None:
        try:
            parts = urlsplit(self.url)
            host = parts.hostname
            allowlist = frozenset(self.allowed_hosts)
            valid = (
                isinstance(self.url, str)
                and not any(ord(c) <= 32 or ord(c) >= 127 for c in self.url)
                and "\\" not in self.url
                and parts.scheme == "https"
                and host is not None
                and _HOST.fullmatch(host) is not None
                and parts.username is None and parts.password is None
                and "?" not in self.url and "#" not in self.url
                and parts.port in (None, 443)
                and bool(allowlist)
                and all(isinstance(h, str) and _HOST.fullmatch(h) for h in allowlist)
                and host in allowlist
            )
        except (TypeError, ValueError, AttributeError):
            valid = False
        if not valid:
            raise DiscoveryError("MCP_ENDPOINT_REJECTED") from None
        object.__setattr__(self, "allowed_hosts", allowlist)


@dataclass(frozen=True)
class DiscoveredTool:
    name: str
    description: str | None
    input_schema: dict


@dataclass(frozen=True)
class ToolCatalog:
    tools: tuple[DiscoveredTool, ...]
    sdk_source: str
    protocol_version: str
    server_name: str | None
    server_version: str | None


def _text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return "".join(c for c in value.strip() if c.isprintable() or c in "\n\t")[:limit]


def _normalize(tool) -> DiscoveredTool:
    if not isinstance(tool.name, str) or not _NAME.fullmatch(tool.name):
        raise DiscoveryError("MCP_CATALOG_REJECTED")
    schema = tool.input_schema
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise DiscoveryError("MCP_CATALOG_REJECTED")
    try:
        Draft202012Validator.check_schema(schema)
        schema = json.loads(json.dumps(schema, sort_keys=True, allow_nan=False))
    except Exception:
        raise DiscoveryError("MCP_CATALOG_REJECTED") from None
    return DiscoveredTool(tool.name, _text(tool.description, 4096), schema)


async def discover_tools(
    endpoint: EndpointConfig, *, http_transport: httpx.AsyncBaseTransport | None = None,
) -> ToolCatalog:
    """Discover all bounded pages; injected HTTP transport is an in-process test seam.

    SDK negotiation may issue server/discover, initialize, and notifications.
    The sole application operation is tools/list. No tool is executed or stored.
    Redirects are disabled using both public HTTP client policy settings.
    All consumed response chunks share a 2 MiB cap, before JSON/SSE parsing;
    non-identity content encodings are rejected before their body is read.
    """
    # Revalidate even if a caller bypassed dataclass construction.
    endpoint = EndpointConfig(endpoint.url, endpoint.allowed_hosts)
    try:
        with anyio.fail_after(DISCOVERY_TIMEOUT_SECONDS):
            budget_transport = _BudgetTransport(
                http_transport if http_transport is not None
                else httpx.AsyncHTTPTransport(trust_env=False),
            )
            async with httpx.AsyncClient(
                transport=budget_transport,
                headers={"Accept-Encoding": "identity"}, trust_env=False,
                timeout=httpx.Timeout(connect=5, write=5, pool=5, read=10),
                follow_redirects=False, max_redirects=0,
            ) as http:
                transport = streamable_http_client(
                    endpoint.url, http_client=http,
                    terminate_on_close=False, max_sse_event_size=MAX_SSE_EVENT_BYTES,
                )
                async with Client(transport, read_timeout_seconds=10, cache=None) as client:
                    tools = {}
                    cursors = set()
                    cursor = None
                    for _ in range(MAX_PAGES):
                        page = await client.list_tools(cursor=cursor)
                        if len(tools) + len(page.tools) > MAX_CATALOG_ENTRIES:
                            raise DiscoveryError("MCP_CATALOG_REJECTED")
                        for raw in page.tools:
                            tool = _normalize(raw)
                            if tool.name in tools:
                                raise DiscoveryError("MCP_CATALOG_REJECTED")
                            tools[tool.name] = tool
                        cursor = page.next_cursor
                        if cursor is None:
                            info = client.server_info
                            catalog = ToolCatalog(
                                tuple(tools[name] for name in sorted(tools)),
                                "mcp/" + version("mcp"), client.protocol_version,
                                _text(info.name, 128) if info else None,
                                _text(info.version, 128) if info else None,
                            )
                            break
                        if cursor in cursors:
                            raise DiscoveryError("MCP_CATALOG_REJECTED")
                        cursors.add(cursor)
                    else:
                        raise DiscoveryError("MCP_CATALOG_REJECTED")
            # SDK background GET errors can be absorbed by its reconnect loop.
            # Wait for SDK and HTTP cleanup before trusting the completed catalog.
            if budget_transport._budget.rejected:
                raise _ResponseRejected()
            return catalog
    except DiscoveryError:
        raise
    except Exception as exc:
        # AnyIO task groups may wrap our fixed catalog rejection on context exit.
        if isinstance(exc, ExceptionGroup) and exc.subgroup(DiscoveryError) is not None:
            raise DiscoveryError("MCP_CATALOG_REJECTED") from None
        raise DiscoveryError("MCP_DISCOVERY_FAILED") from None
