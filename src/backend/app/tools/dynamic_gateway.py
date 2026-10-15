"""Dynamic Tool Gateway with Approval-State-Based Environment Routing.

Enforces T-035:
- Automatically switches between Development and Production endpoints/credentials
  based on the calling Agent's publication status ('draft' | 'approved_published').
- Prevents unauthorized access to production endpoints from draft/unapproved agents.
- Provides protocol adapters for REST/HTTP, SOAP/XML, JDBC View, and TCP Financial Packets.
"""
import asyncio
import hashlib
import json
import time
from typing import Any, Literal
from uuid import UUID, uuid4
from app.errors import AppError
from app.tools.adapters import validate_tool_argument_safety
from app.tools.credentials import decrypt_credential


class DynamicToolGateway:
    def __init__(self):
        # In-memory registry for dynamic tools (persisted in DB table portal.mcp_tool_definitions)
        self._tools: dict[str, dict[str, Any]] = {}
        # tool_id -> {'development': profile_dict, 'production': profile_dict}
        self._profiles: dict[str, dict[str, Any]] = {}
        # Idempotency cache: client_request_id -> args_hash
        self._idempotency_cache: dict[str, str] = {}
        # Audit log buffer
        self._audit_logs: list[dict[str, Any]] = []

    def register_tool(
        self,
        tool_id: str,
        name: str,
        description: str,
        source_type: str,
        input_schema: dict[str, Any],
        raw_meta: dict[str, Any] | None = None,
        dev_profile: dict[str, Any] | None = None,
        prd_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Register a newly auto-wrapped or configured Tool."""
        tool_entry = {
            "tool_id": tool_id,
            "name": name,
            "description": description,
            "source_type": source_type,
            "input_schema": input_schema,
            "raw_meta": raw_meta or {},
            "enabled": True,
            "created_at": time.time(),
        }
        self._tools[tool_id] = tool_entry

        self._profiles[tool_id] = {
            "development": dev_profile or {
                "protocol_type": "rest_http",
                "base_endpoint_url": f"https://dev-api.internal.bank/tools/{tool_id}",
                "credential": {"api_key": "dev_test_mock_token_123"},
                "active": True,
            },
            "production": prd_profile or {
                "protocol_type": "rest_http",
                "base_endpoint_url": f"https://api.internal.bank/tools/{tool_id}",
                "credential": {"api_key": "prd_secure_token_secret_999"},
                "active": True,
            },
        }
        return tool_entry

    def get_tool(self, tool_id: str) -> dict[str, Any] | None:
        return self._tools.get(tool_id)

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "tool_id": t["tool_id"],
                "name": t["name"],
                "description": t["description"],
                "source_type": t["source_type"],
                "input_schema": t["input_schema"],
                "enabled": t["enabled"],
                "has_dev_profile": bool(self._profiles.get(t["tool_id"], {}).get("development")),
                "has_prd_profile": bool(self._profiles.get(t["tool_id"], {}).get("production")),
            }
            for t in self._tools.values()
            if t["enabled"]
        ]

    def set_endpoint_profile(
        self,
        tool_id: str,
        target_env: Literal["development", "production"],
        protocol_type: str,
        base_endpoint_url: str,
        encrypted_credential: str | None = None,
        raw_credential: dict[str, Any] | None = None,
    ) -> None:
        """Update environment-specific endpoint and credentials."""
        if tool_id not in self._tools:
            raise AppError("TOOL_NOT_FOUND", 404)
        if target_env not in ["development", "production"]:
            raise AppError("INVALID_TARGET_ENV", 422)

        cred = raw_credential
        if encrypted_credential and not cred:
            cred = decrypt_credential(encrypted_credential)

        if tool_id not in self._profiles:
            self._profiles[tool_id] = {}

        self._profiles[tool_id][target_env] = {
            "protocol_type": protocol_type,
            "base_endpoint_url": base_endpoint_url,
            "credential": cred,
            "active": True,
        }

    async def invoke_routed(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        publication_status: Literal["draft", "trial", "approved_published"] = "draft",
        client_request_id: str | None = None,
        tenant_id: str = "default_tenant",
        user_id: str = "default_user",
        asset_id: str | None = None,
    ) -> dict[str, Any]:
        """Invoke Tool with dynamic environment routing based on publication status."""
        start_time = time.time()
        tool = self.get_tool(tool_id)
        if not tool:
            raise AppError("TOOL_NOT_FOUND", 404)
        if not tool.get("enabled", True):
            raise AppError("TOOL_DISABLED", 403)

        # 1. Strict argument safety validation
        validate_tool_argument_safety(arguments)

        # 2. Input schema validation
        schema = tool.get("input_schema", {})
        required = schema.get("required", [])
        for req_field in required:
            if req_field not in arguments:
                raise AppError("TOOL_ARGUMENTS_INVALID", 422)

        # 3. Idempotency check
        if client_request_id:
            args_hash = hashlib.sha256(json.dumps(arguments, sort_keys=True).encode("utf-8")).hexdigest()
            prior = self._idempotency_cache.get(client_request_id)
            if prior is not None and prior != args_hash:
                raise AppError("REVISION_CONFLICT", 409)
            self._idempotency_cache[client_request_id] = args_hash

        # 4. Determine Target Environment dynamically
        # Only 'approved_published' can access the Production endpoint!
        if publication_status == "approved_published":
            routed_env: Literal["development", "production"] = "production"
        else:
            routed_env = "development"

        env_profiles = self._profiles.get(tool_id, {})
        profile = env_profiles.get(routed_env)
        if not profile or not profile.get("active", True):
            raise AppError(f"PROFILE_NOT_READY_FOR_{routed_env.upper()}", 503)

        endpoint_url = profile["base_endpoint_url"]
        protocol = profile["protocol_type"]

        try:
            # 5. Protocol execution simulation / fixture dispatch
            execution_result = await self._execute_protocol(
                protocol=protocol,
                endpoint_url=endpoint_url,
                credential=profile.get("credential"),
                arguments=arguments,
                tool_meta=tool.get("raw_meta", {}),
                source_type=tool.get("source_type", "openapi"),
                routed_env=routed_env,
            )
            duration_ms = int((time.time() - start_time) * 1000)

            # Record audit log
            self._audit_logs.append({
                "log_id": str(uuid4()),
                "tenant_id": tenant_id,
                "user_id": user_id,
                "asset_id": asset_id,
                "tool_id": tool_id,
                "publication_status": publication_status,
                "routed_env": routed_env,
                "routed_endpoint": endpoint_url,
                "execution_status": "success",
                "duration_ms": duration_ms,
                "client_request_id": client_request_id,
                "timestamp": time.time(),
            })

            return {
                "tool_id": tool_id,
                "status": "success",
                "routed_env": routed_env,
                "routed_endpoint": endpoint_url,
                "duration_ms": duration_ms,
                "result": execution_result,
            }
        except AppError:
            raise
        except Exception as err:
            duration_ms = int((time.time() - start_time) * 1000)
            self._audit_logs.append({
                "log_id": str(uuid4()),
                "tenant_id": tenant_id,
                "user_id": user_id,
                "asset_id": asset_id,
                "tool_id": tool_id,
                "publication_status": publication_status,
                "routed_env": routed_env,
                "routed_endpoint": endpoint_url,
                "execution_status": "failed",
                "duration_ms": duration_ms,
                "client_request_id": client_request_id,
                "timestamp": time.time(),
            })
            raise AppError("TOOL_EXECUTION_FAILED", 500) from err

    async def _execute_protocol(
        self,
        protocol: str,
        endpoint_url: str,
        credential: Any,
        arguments: dict[str, Any],
        tool_meta: dict[str, Any],
        source_type: str,
        routed_env: str,
    ) -> dict[str, Any]:
        """Dispatch protocol-specific execution with safe deterministic fallback."""
        # Simulated or fixture execution for local development / testing
        await asyncio.sleep(0.01)

        if source_type == "openapi":
            return {
                "source": "openapi_auto_wrapped",
                "environment": routed_env,
                "endpoint_called": endpoint_url,
                "method": tool_meta.get("method", "POST"),
                "applied_arguments": arguments,
                "response_data": {
                    "code": 200,
                    "message": f"Successfully processed via {routed_env.upper()} API",
                    "data": {"status": "ok", "items_processed": 1},
                },
            }
        elif source_type == "wsdl":
            return {
                "source": "wsdl_soap_wrapped",
                "environment": routed_env,
                "endpoint_called": endpoint_url,
                "operation": tool_meta.get("operation_name", "SoapOperation"),
                "soap_response": {
                    "Envelope": {
                        "Body": {
                            "Result": f"SOAP execution success in {routed_env.upper()}",
                            "EchoParams": arguments,
                        }
                    }
                },
            }
        elif source_type == "jdbc":
            return {
                "source": "jdbc_view_wrapped",
                "environment": routed_env,
                "database_target": endpoint_url,
                "read_only": True,
                "rows_returned": 2,
                "rows": [
                    {"id": 1, "status": "ACTIVE", "env": routed_env, "sample_field": "ValA"},
                    {"id": 2, "status": "PENDING", "env": routed_env, "sample_field": "ValB"},
                ],
            }
        elif source_type == "financial_packet":
            return {
                "source": "financial_packet_wrapped",
                "environment": routed_env,
                "socket_host": endpoint_url,
                "packet_code": tool_meta.get("packet_code", "PKT-001"),
                "total_bytes_sent": tool_meta.get("total_length", 120),
                "reply_code": "0000",
                "reply_message": f"정상 승인 완료 ({routed_env})",
                "parsed_response": {
                    "RESP_CODE": "0000",
                    "AUTH_NUM": "88392102",
                    "TIMESTAMP": time.strftime("%Y%m%d%H%M%S"),
                },
            }
        else:
            return {
                "source": "custom_mcp",
                "environment": routed_env,
                "output": f"Executed via {routed_env} endpoint {endpoint_url}",
            }


GLOBAL_DYNAMIC_TOOL_GATEWAY = DynamicToolGateway()
