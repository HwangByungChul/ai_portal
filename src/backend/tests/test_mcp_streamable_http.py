"""Contract-only: official SDK over injected HTTP; no sockets, DB, or fixtures."""
import asyncio
from dataclasses import asdict
import json

import httpx2
import pytest

from app.tools.transports.streamable_http import (
    EndpointConfig, DiscoveryError, discover_tools, MAX_CATALOG_ENTRIES,
)


def endpoint():
    return EndpointConfig("https://catalog.example/mcp", frozenset({"catalog.example"}))


def tool(name, schema=None):
    return {"name": name, "description": "  useful\x00 description  ",
            "inputSchema": {"type": "object", "properties": {}} if schema is None else schema,
            "_meta": {"secret": "DO_NOT_COPY"}, "annotations": {"title": "DO_NOT_COPY"}}


class Peer:
    def __init__(self, tools, *, modern=False, pages=None, failure=None):
        self.tools, self.modern, self.pages, self.failure = tools, modern, pages, failure
        self.requests = []

    def __call__(self, request):
        assert request.url.host == "catalog.example"
        assert request.url.scheme == "https"
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        self.requests.append(request)
        if self.failure:
            return self.failure(request)
        assert request.method == "POST"  # no session-id: no server GET stream
        body = json.loads(request.content)
        method = body["method"]
        assert method in {"server/discover", "initialize", "notifications/initialized", "tools/list"}
        if "id" not in body:
            return httpx2.Response(202)
        if method == "server/discover":
            if not self.modern:
                return httpx2.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
                    "error": {"code": -32601, "message": "legacy"}})
            result = {"supportedVersions": ["2026-07-28"], "capabilities": {"tools": {}}}
        elif method == "initialize":
            result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                "serverInfo": {"name": "fixture", "version": "1", "title": "DO_NOT_COPY"},
                "instructions": "DO_NOT_COPY"}
        else:
            cursor = body.get("params", {}).get("cursor")
            result = self.pages[cursor] if self.pages is not None else {"tools": self.tools}
        if self.modern and method == "tools/list":
            result.update(cacheScope="private", resultType="complete", ttlMs=0)
        return httpx2.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})


def run(peer):
    return asyncio.run(discover_tools(endpoint(), http_transport=httpx2.MockTransport(peer)))


@pytest.mark.parametrize("modern", [False, True])
@pytest.mark.parametrize("names", [[], ["zeta", "alpha"]])
def test_official_sdk_negotiation_empty_sorted_and_sanitized(modern, names):
    peer = Peer([tool(n) for n in names], modern=modern)
    catalog = run(peer)
    assert [t.name for t in catalog.tools] == sorted(names)
    assert catalog.sdk_source == "mcp/2.3.0"
    assert catalog.protocol_version == ("2026-07-28" if modern else "2025-06-18")
    assert catalog.server_name == (None if modern else "fixture")
    assert "DO_NOT_COPY" not in json.dumps(asdict(catalog))
    assert "https://" not in json.dumps(asdict(catalog))
    if names:
        assert catalog.tools[0].description == "useful description"
    assert sum(json.loads(r.content)["method"] == "tools/list" for r in peer.requests) == 1


@pytest.mark.parametrize("url,hosts", [
    ("http://catalog.example/mcp", {"catalog.example"}),
    ("https://other.example/mcp", {"catalog.example"}),
    ("https://sub.catalog.example/mcp", {"catalog.example"}),
    ("https://catalog.example/mcp", set()),
    ("https://catalog.example/mcp", {"*.example"}),
    ("https://name:secret@catalog.example/mcp", {"catalog.example"}),
    ("https://@catalog.example/mcp", {"catalog.example"}),
    ("https://catalog.example/mcp?token=secret", {"catalog.example"}),
    ("https://catalog.example/mcp#secret", {"catalog.example"}),
    ("https://catalog.example/mcp?", {"catalog.example"}),
    ("https://catalog.example:444/mcp", {"catalog.example"}),
    ("https:///mcp", {"catalog.example"}),
    ("https://bad_host/mcp", {"bad_host"}),
    ("https://catalog.example/\nsecret", {"catalog.example"}),
])
def test_endpoint_rejected_with_fixed_error(url, hosts):
    with pytest.raises(DiscoveryError, match="^MCP_ENDPOINT_REJECTED$"):
        EndpointConfig(url, frozenset(hosts))


@pytest.mark.parametrize("tools", [
    [tool("dup"), tool("dup")], [tool(" bad ")], [tool("")],
    [tool("x" * 129)], [tool("x", {"type": "array"})],
    [tool("x", {"type": "object", "properties": 1})],
    [tool("x", [])], [tool("x", True)],
    [tool(str(n)) for n in range(MAX_CATALOG_ENTRIES + 1)],
])
def test_malformed_catalog_fixed_safe_error(tools):
    with pytest.raises(DiscoveryError) as caught:
        run(Peer(tools))
    assert str(caught.value) in {"MCP_CATALOG_REJECTED", "MCP_DISCOVERY_FAILED"}
    assert "DO_NOT_COPY" not in str(caught.value)


def test_pagination_and_duplicate_across_pages():
    pages = {None: {"tools": [tool("z")], "nextCursor": "next"},
             "next": {"tools": [tool("a")]}}
    assert [t.name for t in run(Peer([], pages=pages)).tools] == ["a", "z"]
    pages["next"]["tools"] = [tool("z")]
    with pytest.raises(DiscoveryError, match="MCP_CATALOG_REJECTED"):
        run(Peer([], pages=pages))


def test_repeating_cursor_rejected():
    pages = {None: {"tools": [], "nextCursor": "next"},
             "next": {"tools": [], "nextCursor": "next"}}
    with pytest.raises(DiscoveryError, match="MCP_CATALOG_REJECTED"):
        run(Peer([], pages=pages))


@pytest.mark.parametrize("target", ["/elsewhere", "https://other.example/mcp"])
def test_redirect_never_followed_even_same_origin(target):
    peer = Peer([], failure=lambda r: httpx2.Response(307, headers={"Location": target}))
    with pytest.raises(DiscoveryError, match="^MCP_DISCOVERY_FAILED$"):
        run(peer)
    assert all(str(r.url) == "https://catalog.example/mcp" for r in peer.requests)
    # SDK negotiation fallback can issue initialize; no redirect target is requested.
    assert len(peer.requests) <= 2


def test_transport_error_does_not_leak_details_or_retry():
    def fail(request):
        raise httpx2.ConnectError("secret endpoint response token", request=request)
    peer = Peer([], failure=fail)
    with pytest.raises(DiscoveryError, match="^MCP_DISCOVERY_FAILED$"):
        run(peer)
    assert len(peer.requests) == 1


def test_oversize_sse_event_is_rejected_by_official_transport():
    peer = Peer([])
    def handler(request):
        body = json.loads(request.content)
        if body["method"] == "tools/list":
            event = {"jsonrpc": "2.0", "id": body["id"], "result": {
                "tools": [tool("large", {"type": "object", "description": "x" * 270000})]}}
            return httpx2.Response(200, headers={"content-type": "text/event-stream"},
                                  content="event: message\ndata: " + json.dumps(event) + "\n\n")
        return peer(request)
    with pytest.raises(DiscoveryError, match="^MCP_DISCOVERY_FAILED$"):
        asyncio.run(discover_tools(endpoint(), http_transport=httpx2.MockTransport(handler)))


def test_global_timeout_bounds_discovery(monkeypatch):
    from app.tools.transports import streamable_http
    import anyio
    monkeypatch.setattr(streamable_http, "DISCOVERY_TIMEOUT_SECONDS", 0.01)
    calls = []
    async def slow(request):
        calls.append(request)
        await anyio.sleep(1)
        raise AssertionError("deadline did not cancel HTTP call")
    with pytest.raises(DiscoveryError, match="^MCP_DISCOVERY_FAILED$"):
        asyncio.run(discover_tools(endpoint(), http_transport=httpx2.MockTransport(slow)))
    assert len(calls) == 1


def test_http_timeouts_and_session_lifetime_are_local():
    peer = Peer([])
    run(peer)
    run(peer)
    methods = [json.loads(r.content)["method"] for r in peer.requests]
    assert methods.count("server/discover") == 2
    assert methods.count("tools/list") == 2
    for request in peer.requests:
        timeouts = request.extensions["timeout"]
        assert all(0 < timeouts[key] <= 10 for key in ("connect", "write", "pool", "read"))


class TrackedStream(httpx2.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.reads = 0
        self.close_calls = 0

    async def __aiter__(self):
        for chunk in self.chunks:
            self.reads += 1
            yield chunk

    async def aclose(self):
        self.close_calls += 1


def assert_discovery_failed(handler):
    with pytest.raises(DiscoveryError, match="^MCP_DISCOVERY_FAILED$") as caught:
        asyncio.run(discover_tools(endpoint(), http_transport=httpx2.MockTransport(handler)))
    assert caught.value.__suppress_context__
    assert caught.value.__cause__ is None
    assert "catalog.example" not in str(caught.value)
    assert "BODY_SECRET" not in str(caught.value)


@pytest.mark.parametrize("content_type", ["application/json", "text/event-stream"])
def test_response_budget_rejects_large_json_and_sse_and_closes(content_type):
    from app.tools.transports.streamable_http import MAX_RESPONSE_BYTES
    peer = Peer([])
    # Small SSE comment events exercise the total cap independently of the
    # SDK's separate maximum event size.
    chunk = b" " * 32768 if content_type == "application/json" else b":" + b"x" * 32765 + b"\n\n"
    chunks = [chunk] * (MAX_RESPONSE_BYTES // len(chunk) + 1)
    stream = TrackedStream([*chunks, b"BODY_SECRET must never be read"])
    negotiation_bytes = []

    def handler(request):
        assert request.headers["accept-encoding"] == "identity"
        body = json.loads(request.content)
        if body["method"] == "tools/list":
            payload = json.dumps({"jsonrpc": "2.0", "id": body["id"],
                                  "result": {"tools": [], "_meta": {"secret": "BODY_SECRET"}}}).encode()
            stream.chunks[-1] = (payload if content_type == "application/json"
                                 else b"event: message\ndata: " + payload + b"\n\n")
            return httpx2.Response(200, headers={"content-type": content_type}, stream=stream)
        response = peer(request)
        negotiation_bytes.append(len(response.content))
        return response

    assert_discovery_failed(handler)
    expected_reads = (MAX_RESPONSE_BYTES - sum(negotiation_bytes)) // len(chunk) + 1
    assert stream.reads == expected_reads
    assert stream.reads <= len(chunks)  # final valid JSON/SSE payload is unread
    assert stream.close_calls == 1


def test_budget_is_cumulative_across_negotiation_and_list_pages(monkeypatch):
    from app.tools.transports import streamable_http
    monkeypatch.setattr(streamable_http, "MAX_RESPONSE_BYTES", 2000)
    pages = {None: {"tools": [], "nextCursor": "next"}, "next": {"tools": []}}
    peer = Peer([], pages=pages)
    streams = []

    def handler(request):
        response = peer(request)
        if response.status_code == 202:
            return response
        # Each body fits independently. Negotiation and the first list page
        # use 1800 bytes; page two's first chunk crosses the 2000-byte cap.
        content = response.content
        assert len(content) < 300
        chunks = [content.ljust(300), b" " * 300]
        if len(streams) == 3:
            chunks.append(b"BODY_SECRET must never be read")
        stream = TrackedStream(chunks)
        streams.append(stream)
        return httpx2.Response(200, headers=response.headers, stream=stream)

    assert_discovery_failed(handler)
    assert [s.reads for s in streams] == [2, 2, 2, 1]
    assert all(s.close_calls == 1 for s in streams)
    assert [json.loads(r.content)["method"] for r in peer.requests] == [
        "server/discover", "initialize", "notifications/initialized", "tools/list", "tools/list"]


@pytest.mark.parametrize("encoding", ["gzip", "br", "deflate", "identity, gzip", ""])
def test_non_identity_encoding_rejected_before_read_and_closed(encoding):
    stream = TrackedStream([b"BODY_SECRET"])
    requests = []
    def handler(request):
        requests.append(request)
        assert request.headers["accept-encoding"] == "identity"
        return httpx2.Response(200, headers={"content-type": "application/json",
                                           "content-encoding": encoding}, stream=stream)
    assert_discovery_failed(handler)
    assert stream.reads == 0
    assert stream.close_calls == 1
    assert len(requests) == 1


def test_exact_byte_budget_succeeds_and_new_call_has_fresh_budget(monkeypatch):
    from app.tools.transports import streamable_http
    peer = Peer([], modern=True)
    streams = []
    monkeypatch.setattr(streamable_http, "MAX_RESPONSE_BYTES", 1200)
    def handler(request):
        response = peer(request)
        assert request.headers["accept-encoding"] == "identity"
        content = response.content
        assert len(content) < 600
        stream = TrackedStream([content.ljust(600)])
        streams.append(stream)
        return httpx2.Response(response.status_code, headers={"content-type": "application/json",
                                                           "content-encoding": " Identity "}, stream=stream)
    for _ in range(2):
        assert asyncio.run(discover_tools(endpoint(), http_transport=httpx2.MockTransport(handler))).tools == ()
    assert len(streams) == 4
    assert all(s.reads == s.close_calls == 1 for s in streams)


@pytest.mark.parametrize("outcome", ["timeout", "cancel", "read_error"])
def test_response_stream_closed_on_timeout_cancellation_and_read_error(monkeypatch, outcome):
    import anyio
    from app.tools.transports import streamable_http
    entered = asyncio.Event()
    class InterruptedStream(TrackedStream):
        async def __aiter__(self):
            entered.set()
            if outcome == "read_error":
                raise httpx2.ReadError("BODY_SECRET")
            await anyio.sleep_forever()
            yield b"unreachable"
        async def aclose(self):
            # This cancellation point also proves closure is shielded.
            await anyio.sleep(0)
            await super().aclose()
    stream = InterruptedStream([])
    def handler(request):
        return httpx2.Response(200, headers={"content-type": "application/json"}, stream=stream)
    if outcome == "timeout":
        monkeypatch.setattr(streamable_http, "DISCOVERY_TIMEOUT_SECONDS", 0.02)
    if outcome == "cancel":
        async def cancel_discovery():
            task = asyncio.create_task(discover_tools(endpoint(), http_transport=httpx2.MockTransport(handler)))
            await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        asyncio.run(cancel_discovery())
    else:
        assert_discovery_failed(handler)
    assert stream.close_calls == 1


@pytest.mark.parametrize("encoding", [None, "gzip", "br", "deflate", "identity, gzip", ""])
def test_concurrent_get_rejection_fails_after_valid_list_body_is_consumed(monkeypatch, encoding):
    from app.tools.transports import streamable_http
    monkeypatch.setattr(streamable_http, "MAX_RESPONSE_BYTES", 2000)
    peer = Peer([])
    list_consumed = asyncio.Event()
    get_closed = asyncio.Event()
    get_requests = []
    list_streams = []

    class GetStream(TrackedStream):
        async def aclose(self):
            await super().aclose()
            get_closed.set()

    class ListStream(TrackedStream):
        async def __aiter__(self):
            async for chunk in super().__aiter__():
                yield chunk
            # The valid list bytes have passed the shared budget already.
            # Complete the response only after the concurrent GET is rejected.
            list_consumed.set()
            await get_closed.wait()

    get_stream = GetStream([b":" + b"x" * 1997 + b"\n\n", b"BODY_SECRET unread"])

    async def handler(request):
        assert request.headers["accept-encoding"] == "identity"
        if request.method == "GET":
            assert request.headers["mcp-session-id"] == "fixture-session"
            get_requests.append(request)
            await list_consumed.wait()
            headers = {"content-type": "text/event-stream"}
            if encoding is not None:
                headers["content-encoding"] = encoding
            return httpx2.Response(200, headers=headers, stream=get_stream)
        response = peer(request)
        method = json.loads(request.content)["method"]
        if method == "initialize":
            response.headers["mcp-session-id"] = "fixture-session"
        elif method == "tools/list":
            stream = ListStream([response.content])
            list_streams.append(stream)
            return httpx2.Response(200, headers=response.headers, stream=stream)
        return response

    assert_discovery_failed(handler)
    assert len(get_requests) == 1
    assert len(list_streams) == 1
    assert list_consumed.is_set()
    assert list_streams[0].reads == list_streams[0].close_calls == 1
    assert get_stream.reads == (1 if encoding is None else 0)
    assert get_stream.close_calls == 1
