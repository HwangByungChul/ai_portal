"""Auto-Wrapping and Dynamic Tool Gateway HTTP Routes."""
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictStr
from fastapi import APIRouter, Request
from app.errors import AppError, response
from app.tenants.routes import context
from app.tools.parsers.openapi_parser import parse_openapi_spec
from app.tools.parsers.wsdl_parser import parse_wsdl_spec
from app.tools.parsers.jdbc_parser import parse_jdbc_spec
from app.tools.parsers.packet_parser import parse_packet_spec
from app.tools.dynamic_gateway import DynamicToolGateway, GLOBAL_DYNAMIC_TOOL_GATEWAY
from app.tools.dynamic_repository import DynamicToolRepository

router = APIRouter(prefix="/api/v1/tools")


class AutoWrapParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_type: Literal["openapi", "wsdl", "jdbc", "financial_packet"]
    raw_content: Any = Field(description="Raw specification (JSON string, XML string, or dictionary)")


class EndpointProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_type: Literal["mcp_http_sse", "rest_http", "soap_xml", "tcp_socket", "jdbc_view"] = "rest_http"
    base_endpoint_url: StrictStr


class AutoWrapRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_id: StrictStr
    name: StrictStr
    description: StrictStr
    source_type: Literal["openapi", "wsdl", "jdbc", "financial_packet", "custom_mcp"]
    input_schema: dict[str, Any]
    raw_meta: dict[str, Any] = Field(default_factory=dict)
    dev_profile: EndpointProfileInput
    prd_profile: EndpointProfileInput


class DynamicToolInvokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    arguments: dict[str, Any] = Field(default_factory=dict)
    client_request_id: UUID | None = None


class AutoWrapSimulateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_id: StrictStr
    name: StrictStr
    description: StrictStr
    source_type: Literal["openapi", "wsdl", "jdbc", "financial_packet", "custom_mcp"]
    input_schema: dict[str, Any]
    raw_meta: dict[str, Any] = Field(default_factory=dict)
    dev_profile: EndpointProfileInput
    arguments: dict[str, Any] = Field(default_factory=dict)


class ImportMCPToolsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    server_url: StrictStr
    allowed_hosts: list[StrictStr] = Field(min_length=1)
    tool_names_filter: list[StrictStr] | None = None


def _require_tool_admin(ctx):
    if getattr(ctx, "effective_role", None) not in {"TADMIN", "PADMIN"}:
        raise AppError("TOOL_NOT_PERMITTED", 403)


@router.post("/auto-wrap/parse")
async def parse_tool_spec(request: Request, body: AutoWrapParseRequest):
    """Parse raw interface specification and generate wrapped MCP Tool schemas."""
    await context(request)  # Ensure authenticated session
    st = body.source_type
    raw = body.raw_content

    if st == "openapi":
        tools = parse_openapi_spec(raw)
        return response(request, {"source_type": st, "tools": tools, "count": len(tools)})
    elif st == "wsdl":
        if not isinstance(raw, str):
            raise AppError("WSDL_CONTENT_MUST_BE_STRING", 422)
        tools = parse_wsdl_spec(raw)
        return response(request, {"source_type": st, "tools": tools, "count": len(tools)})
    elif st == "jdbc":
        if not isinstance(raw, dict):
            raise AppError("JDBC_CONTENT_MUST_BE_OBJECT", 422)
        tool = parse_jdbc_spec(raw)
        return response(request, {"source_type": st, "tools": [tool], "count": 1})
    elif st == "financial_packet":
        if not isinstance(raw, dict):
            raise AppError("PACKET_CONTENT_MUST_BE_OBJECT", 422)
        tool = parse_packet_spec(raw)
        return response(request, {"source_type": st, "tools": [tool], "count": 1})
    else:
        raise AppError("UNSUPPORTED_SOURCE_TYPE", 422)


@router.post("/auto-wrap/simulate")
async def simulate_auto_wrapped_tool(request: Request, body: AutoWrapSimulateRequest):
    """Simulate an unsaved definition in a request-local fixture adapter."""
    ctx = await context(request, write=True)
    _require_tool_admin(ctx)
    gateway = DynamicToolGateway()
    gateway.register_tool(
        tool_id=body.tool_id,
        name=body.name,
        description=body.description,
        source_type=body.source_type,
        input_schema=body.input_schema,
        raw_meta=body.raw_meta,
        dev_profile=body.dev_profile.model_dump(),
        tenant_id=str(ctx.tenant_id),
    )
    result = await gateway.invoke_routed(
        tool_id=body.tool_id,
        arguments=body.arguments,
        publication_status="draft",
        tenant_id=str(ctx.tenant_id),
        user_id=str(ctx.user_id),
    )
    return response(request, result)


@router.post("/auto-wrap/register")
async def register_auto_wrapped_tool(request: Request, body: AutoWrapRegisterRequest):
    """Register wrapped tool and bind dev/prd endpoint profiles."""
    ctx = await context(request, write=True)
    _require_tool_admin(ctx)
    tool_entry = await DynamicToolRepository(request.app.state.pool).register(
        ctx,
        tool_id=body.tool_id,
        name=body.name,
        description=body.description,
        source_type=body.source_type,
        input_schema=body.input_schema,
        raw_meta=body.raw_meta,
        dev_profile=body.dev_profile.model_dump(),
        prd_profile=body.prd_profile.model_dump(),
    )
    # Keep the development fixture adapter usable in this process. Database
    # persistence is the registry source; this cache is never production routing.
    GLOBAL_DYNAMIC_TOOL_GATEWAY.register_tool(
        tool_id=body.tool_id,
        name=body.name,
        description=body.description,
        source_type=body.source_type,
        input_schema=body.input_schema,
        raw_meta=body.raw_meta,
        dev_profile=body.dev_profile.model_dump(),
        prd_profile=body.prd_profile.model_dump(),
        tenant_id=str(ctx.tenant_id),
    )
    return response(request, {"status": "registered", "tool": tool_entry})


@router.get("/dynamic")
async def list_dynamic_tools(request: Request):
    """List registered dynamic tools with environment capability badges."""
    ctx = await context(request)
    _require_tool_admin(ctx)
    tools = await DynamicToolRepository(request.app.state.pool).list(ctx)
    return response(request, {"items": tools, "total": len(tools)})


@router.post("/dynamic/{tool_id}/invoke")
async def invoke_dynamic_tool(request: Request, tool_id: str, body: DynamicToolInvokeRequest):
    """Run a development-profile fixture simulation; never invoke a production endpoint."""
    ctx = await context(request, write=True)
    _require_tool_admin(ctx)
    repository = DynamicToolRepository(request.app.state.pool)
    persisted = await repository.simulation_profile(ctx, tool_id)
    GLOBAL_DYNAMIC_TOOL_GATEWAY.register_tool(
        tool_id=persisted["tool_id"],
        name=persisted["name"],
        description=persisted["description"],
        source_type=persisted["source_type"],
        input_schema=persisted["input_schema"],
        raw_meta=persisted["raw_meta"],
        dev_profile=persisted["dev_profile"],
        prd_profile=persisted["prd_profile"],
        tenant_id=str(ctx.tenant_id),
    )
    # This wizard is currently a simulation surface. Never accept a client supplied
    # publication state or asset identity as authority to select a production profile.
    result = await GLOBAL_DYNAMIC_TOOL_GATEWAY.invoke_routed(
        tool_id=tool_id,
        arguments=body.arguments,
        publication_status="draft",
        client_request_id=str(body.client_request_id) if body.client_request_id else None,
        tenant_id=str(ctx.tenant_id),
        user_id=str(ctx.user_id),
    )
    return response(request, result)


@router.post("/import-mcp")
async def import_mcp_tools(request: Request, body: ImportMCPToolsRequest):
    """Discover tools from remote Streamable HTTP/SSE MCP server and register them."""
    import urllib.parse
    ctx = await context(request, write=True)
    _require_tool_admin(ctx)

    parsed = urllib.parse.urlparse(body.server_url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise AppError("TOOL_ENDPOINT_INVALID", 400)

    if parsed.netloc not in body.allowed_hosts:
        raise AppError("TOOL_ENDPOINT_INVALID", 400)

    from app.tools.transports.streamable_http import discover_tools, EndpointConfig
    catalog = await discover_tools(EndpointConfig(body.server_url, frozenset(body.allowed_hosts)))

    imported_tools = []
    skipped_count = 0

    for tool in catalog.tools:
        if body.tool_names_filter and tool.name not in body.tool_names_filter:
            skipped_count += 1
            continue

        tool_id = tool.name
        dev_profile = {
            "protocol_type": "mcp_http_sse",
            "base_endpoint_url": body.server_url,
            "active": True,
        }
        prd_profile = {
            "protocol_type": "mcp_http_sse",
            "base_endpoint_url": body.server_url,
            "active": True,
        }

        entry = GLOBAL_DYNAMIC_TOOL_GATEWAY.register_tool(
            tool_id=tool_id,
            name=tool.name,
            description=tool.description,
            source_type="custom_mcp",
            input_schema=tool.input_schema,
            raw_meta={"sdk_source": "modelcontextprotocol", "server_url": body.server_url},
            dev_profile=dev_profile,
            prd_profile=prd_profile,
            tenant_id=str(ctx.tenant_id),
        )
        imported_tools.append({
            "tool_id": tool_id,
            "name": tool.name,
            "status": "imported",
        })

    return response(request, {
        "status": "success",
        "server_url": body.server_url,
        "imported_tools": imported_tools,
        "skipped_count": skipped_count,
        "total_discovered": len(catalog.tools),
    })

