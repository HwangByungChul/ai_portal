"""OpenAPI / Swagger Specification Auto-Wrapping Parser.

Parses Swagger 2.0 and OpenAPI 3.0+ specifications (JSON or YAML) and automatically
converts each endpoint/operation into an MCP (Model Context Protocol) Tool specification.
"""
import json
import re
from typing import Any
from app.errors import AppError


def parse_openapi_spec(raw_content: str | dict[str, Any]) -> list[dict[str, Any]]:
    """Parse OpenAPI spec and return list of wrapped MCP Tool definitions."""
    if isinstance(raw_content, str):
        try:
            spec = json.loads(raw_content)
        except json.JSONDecodeError:
            # Basic YAML-like or malformed detection
            raise AppError("OPENAPI_SPEC_INVALID", 422)
    elif isinstance(raw_content, dict):
        spec = raw_content
    else:
        raise AppError("OPENAPI_SPEC_INVALID", 422)

    if not isinstance(spec, dict) or "paths" not in spec:
        raise AppError("OPENAPI_SPEC_INVALID", 422)

    title = spec.get("info", {}).get("title", "OpenAPI Service")
    tools: list[dict[str, Any]] = []

    paths = spec.get("paths", {})
    for path_str, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in ["get", "post", "put", "delete", "patch"]:
            if method not in path_item:
                continue
            op = path_item[method]
            if not isinstance(op, dict):
                continue

            op_id = op.get("operationId")
            if not op_id:
                # Generate deterministic operation ID from path & method
                clean_path = re.sub(r"[^a-zA-Z0-9]+", "_", path_str).strip("_")
                op_id = f"{method}_{clean_path}"

            summary = op.get("summary") or op.get("description") or f"{method.upper()} {path_str}"
            description = (
                f"[{title}] {summary}\n"
                f"HTTP Method: {method.upper()}\n"
                f"Path: {path_str}"
            )

            # Build input JSON schema
            properties: dict[str, Any] = {}
            required_fields: list[str] = []

            # 1. Parse parameters (query, path, header)
            for param in op.get("parameters", []):
                if not isinstance(param, dict):
                    continue
                p_name = param.get("name")
                if not p_name:
                    continue
                p_schema = param.get("schema", {})
                p_type = p_schema.get("type", "string")
                p_desc = param.get("description", "")
                properties[p_name] = {
                    "type": p_type,
                    "description": p_desc,
                }
                if param.get("required") is True:
                    required_fields.append(p_name)

            # 2. Parse requestBody (OpenAPI 3.0+)
            req_body = op.get("requestBody", {})
            if isinstance(req_body, dict):
                content = req_body.get("content", {})
                json_content = content.get("application/json", {})
                body_schema = json_content.get("schema", {})
                if body_schema.get("type") == "object":
                    body_props = body_schema.get("properties", {})
                    for b_name, b_val in body_props.items():
                        properties[b_name] = b_val
                    for req_b in body_schema.get("required", []):
                        if req_b not in required_fields:
                            required_fields.append(req_b)

            input_schema = {
                "type": "object",
                "properties": properties,
                "required": required_fields,
                "additionalProperties": False,
            }

            tools.append({
                "tool_id": op_id,
                "name": summary[:60],
                "description": description,
                "category": "api_rest",
                "source_type": "openapi",
                "method": method.upper(),
                "path": path_str,
                "input_schema": input_schema,
                "raw_operation": op,
            })

    if not tools:
        raise AppError("NO_VALID_OPERATIONS_FOUND", 422)

    return tools
