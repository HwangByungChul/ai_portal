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
from app.tools.dynamic_gateway import GLOBAL_DYNAMIC_TOOL_GATEWAY

router = APIRouter(prefix="/api/v1/tools")


class AutoWrapParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_type: Literal["openapi", "wsdl", "jdbc", "financial_packet"]
    raw_content: Any = Field(description="Raw specification (JSON string, XML string, or dictionary)")


class EndpointProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_type: Literal["mcp_http_sse", "rest_http", "soap_xml", "tcp_socket", "jdbc_view"] = "rest_http"
    base_endpoint_url: StrictStr
    credential: dict[str, Any] | None = None


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
    publication_status: Literal["draft", "trial", "approved_published"] = "draft"
    client_request_id: UUID | None = None
    asset_id: str | None = None


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


@router.post("/auto-wrap/register")
async def register_auto_wrapped_tool(request: Request, body: AutoWrapRegisterRequest):
    """Register wrapped tool and bind dev/prd endpoint profiles."""
    ctx = await context(request, write=True)
    tool_entry = GLOBAL_DYNAMIC_TOOL_GATEWAY.register_tool(
        tool_id=body.tool_id,
        name=body.name,
        description=body.description,
        source_type=body.source_type,
        input_schema=body.input_schema,
        raw_meta=body.raw_meta,
        dev_profile=body.dev_profile.model_dump(),
        prd_profile=body.prd_profile.model_dump(),
    )
    return response(request, {"status": "registered", "tool": tool_entry})


@router.get("/dynamic")
async def list_dynamic_tools(request: Request):
    """List registered dynamic tools with environment capability badges."""
    await context(request)
    tools = GLOBAL_DYNAMIC_TOOL_GATEWAY.list_tools()
    return response(request, {"items": tools, "total": len(tools)})


@router.post("/dynamic/{tool_id}/invoke")
async def invoke_dynamic_tool(request: Request, tool_id: str, body: DynamicToolInvokeRequest):
    """Invoke tool with automatic dev/prd routing based on agent publication status."""
    ctx = await context(request, write=True)
    tenant_id = str(ctx.get("tenant_id", "default_tenant"))
    user_id = str(ctx.get("user_id", "default_user"))

    result = await GLOBAL_DYNAMIC_TOOL_GATEWAY.invoke_routed(
        tool_id=tool_id,
        arguments=body.arguments,
        publication_status=body.publication_status,
        client_request_id=str(body.client_request_id) if body.client_request_id else None,
        tenant_id=tenant_id,
        user_id=user_id,
        asset_id=body.asset_id,
    )
    return response(request, result)
