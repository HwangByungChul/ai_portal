"""Standard Tool & MCP Gateway Registry Module."""
import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable
from app.errors import AppError
from app.tools.adapters import (
    BaseToolAdapter,
    FixtureToolAdapter,
    validate_tool_argument_safety,
)

@dataclass
class ToolDefinition:
    tool_id: str
    name: str
    description: str
    category: str
    arg_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], dict[str, Any]]
    timeout_seconds: int = 10
    enabled: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "arg_schema": self.arg_schema,
            "timeout_seconds": self.timeout_seconds,
            "enabled": self.enabled,
        }


def make_approved_tools(adapter: BaseToolAdapter) -> dict[str, ToolDefinition]:
    return {
        "financial_product_lookup": ToolDefinition(
            tool_id="financial_product_lookup",
            name="금융 상품 정보 조회",
            description="예금, 적금, 대출 등 표준 금융 상품의 금리 및 조건을 조회합니다.",
            category="financial",
            arg_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "category": {"type": "string", "enum": ["deposit", "savings", "loan", "all"]},
                    "query": {"type": "string", "maxLength": 100},
                },
            },
            handler=adapter.handle_financial_product_lookup,
        ),
        "kb_rule_query": ToolDefinition(
            tool_id="kb_rule_query",
            name="내부 업무 규정 검색",
            description="정보보호, AI 거버넌스, 데이터 반입 등 사내 표준 규정을 검색합니다.",
            category="regulation",
            arg_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "section": {"type": "string", "maxLength": 100},
                    "keyword": {"type": "string", "maxLength": 100},
                },
            },
            handler=adapter.handle_kb_rule_query,
        ),
        "data_view_reader": ToolDefinition(
            tool_id="data_view_reader",
            name="데이터 가상화 뷰 조회",
            description="사전 승인된 읽기 전용 데이터 가상화 뷰(지점별 통계 등)를 안전하게 조회합니다.",
            category="data_view",
            arg_schema={
                "type": "object",
                "required": ["view_name"],
                "additionalProperties": False,
                "properties": {
                    "view_name": {"type": "string", "maxLength": 100},
                },
            },
            handler=adapter.handle_data_view_reader,
        ),
    }


class ToolRegistry:
    def __init__(
        self,
        adapter: BaseToolAdapter | None = None,
        tools: dict[str, ToolDefinition] | None = None,
    ):
        self._adapter = adapter or FixtureToolAdapter()
        self._tools = dict(tools or make_approved_tools(self._adapter))
        self._idempotency_cache: dict[str, str] = {}  # client_request_id -> args_hash

    def get(self, tool_id: str) -> ToolDefinition | None:
        return self._tools.get(tool_id)

    def list_public(self) -> list[dict[str, Any]]:
        return [t.to_public_dict() for t in self._tools.values() if t.enabled]

    def validate(self,tool_id,args):
        tool=self.get(tool_id)
        if tool is None:raise AppError('TOOL_NOT_FOUND',404)
        if not tool.enabled:raise AppError('TOOL_DISABLED',403)
        if type(args) is not dict:raise AppError('TOOL_ARGUMENTS_INVALID',422)
        try:
            raw=json.dumps(args,ensure_ascii=False,allow_nan=False).encode('utf-8')
        except (TypeError,ValueError,UnicodeError):raise AppError('TOOL_ARGUMENTS_INVALID',422) from None
        if len(raw)>32768:raise AppError('TOOL_ARGUMENTS_INVALID',422)
        validate_tool_argument_safety(args)
        schema=tool.arg_schema;props=schema.get('properties',{})
        if schema.get('additionalProperties') is False and set(args)-set(props):raise AppError('TOOL_ARGUMENTS_INVALID',422)
        if any(k not in args for k in schema.get('required',[])):raise AppError('TOOL_ARGUMENTS_INVALID',422)
        for name,value in args.items():
            spec=props.get(name,{})
            # Current server-approved Tools accept only bounded string properties.
            if spec.get('type')!='string' or type(value) is not str:raise AppError('TOOL_ARGUMENTS_INVALID',422)
            if len(value)>spec.get('maxLength',1000) or ('enum' in spec and value not in spec['enum']):raise AppError('TOOL_ARGUMENTS_INVALID',422)
        return tool

    async def invoke(
        self,
        tool_id: str,
        args: dict[str, Any],
        client_request_id: str | None = None,
    ) -> dict[str, Any]:
        tool = self.validate(tool_id,args)
        if not tool:
            raise AppError("TOOL_NOT_FOUND", 404)
        if not tool.enabled:
            raise AppError("TOOL_DISABLED", 403)

        # 1. Strict Schema & Safety Validation
        validate_tool_argument_safety(args)

        allowed_props = set(tool.arg_schema.get("properties", {}).keys())
        if tool.arg_schema.get("additionalProperties") is False:
            extra_keys = set(args.keys()) - allowed_props
            if extra_keys:
                raise AppError("TOOL_ARGUMENTS_INVALID", 422)

        required = tool.arg_schema.get("required", [])
        for req_field in required:
            if req_field not in args:
                raise AppError("TOOL_ARGUMENTS_INVALID", 422)

        # Check enum constraints if defined
        for prop, spec in tool.arg_schema.get("properties", {}).items():
            if prop in args and "enum" in spec:
                if args[prop] not in spec["enum"]:
                    raise AppError("TOOL_ARGUMENTS_INVALID", 422)

        # 2. Idempotency Check
        if client_request_id:
            args_hash = hashlib.sha256(
                json.dumps(args, sort_keys=True).encode("utf-8")
            ).hexdigest()
            prior_hash = self._idempotency_cache.get(client_request_id)
            if prior_hash is not None and prior_hash != args_hash:
                raise AppError("REVISION_CONFLICT", 409)
            self._idempotency_cache[client_request_id] = args_hash

        try:
            # 3. Enforce timeout
            result = await asyncio.wait_for(
                asyncio.to_thread(tool.handler, args),
                timeout=tool.timeout_seconds,
            )
            return {
                "tool_id": tool.tool_id,
                "status": "success",
                "result": result,
            }
        except asyncio.TimeoutError:
            raise AppError("TOOL_TIMEOUT", 504) from None
        except AppError:
            raise
        except Exception as err:
            raise AppError("TOOL_EXECUTION_FAILED", 500) from err


GLOBAL_TOOL_REGISTRY = ToolRegistry()
