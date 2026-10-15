"""Guardrail API routes — policy management and violation audit.

PADMIN-only endpoints for viewing/updating guardrail policies and
querying violation audit history.
"""
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr
from typing import Literal

from app.errors import AppError, response
from app.tenants.routes import context
from app.guardrails.engine import (
    get_policy,
    update_policy,
    evaluate_input,
    evaluate_output,
    text_hash,
    REVISION,
    GuardrailResult,
)

router = APIRouter(prefix="/api/v1")

# ---------------------------------------------------------------------------
# In-memory violation audit log (append-only, no raw text)
# ---------------------------------------------------------------------------
_VIOLATIONS: list[dict] = []
MAX_VIOLATIONS = 10000


def record_violation(
    tenant_id: str,
    user_id: str,
    direction: str,
    rule_ids: tuple[str, ...],
    content_hash: str,
    policy_revision: str,
) -> None:
    """Append a violation record. Oldest entries are evicted when limit is reached."""
    entry = {
        "violation_id": str(uuid4()),
        "tenant_id": tenant_id,
        "user_id": user_id,
        "direction": direction,
        "rule_ids": list(rule_ids),
        "content_hash": content_hash,
        "policy_revision": policy_revision,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _VIOLATIONS.append(entry)
    if len(_VIOLATIONS) > MAX_VIOLATIONS:
        _VIOLATIONS.pop(0)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class PolicyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: StrictInt = Field(ge=0)
    input_enabled: StrictBool | None = None
    output_enabled: StrictBool | None = None
    pii_severity: Literal["block", "warn", "log"] | None = None
    injection_severity: Literal["block", "warn", "log"] | None = None
    forbidden_severity: Literal["block", "warn", "log"] | None = None
    output_pii_action: Literal["mask", "block"] | None = None


from app.guardrails.repository import GuardrailRepository

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/admin/guardrails/policies")
async def get_guardrail_policies(request: Request):
    ctx = await context(request)
    if ctx.effective_role != "PADMIN":
        raise AppError("MANAGEMENT_DENIED", 403)
    
    pool = getattr(request.app.state, "pool", None)
    if pool is not None:
        repo = GuardrailRepository(pool)
        data = await repo.get_policy(ctx)
        return response(request, {
            "revision": data.get("revision", 1),
            "engine_revision": data.get("engine_revision", REVISION),
            "input_enabled": data.get("input_enabled", True),
            "output_enabled": data.get("output_enabled", True),
            "pii_severity": data.get("pii_severity", "block"),
            "injection_severity": data.get("injection_severity", "block"),
            "forbidden_severity": data.get("forbidden_severity", "block"),
            "output_pii_action": data.get("output_pii_action", "mask"),
            "input_rules": [
                "PII_RRN", "PII_PHONE", "PII_EMAIL", "PII_ACCOUNT",
                "PROMPT_INJECTION", "FORBIDDEN_CONTENT",
            ],
            "output_rules": [
                "PII_RRN", "PII_PHONE", "PII_EMAIL", "PII_ACCOUNT",
                "FORBIDDEN_CONTENT",
            ],
        })

    policy = get_policy()
    return response(request, {
        "revision": policy.revision,
        "engine_revision": REVISION,
        "input_enabled": policy.input_enabled,
        "output_enabled": policy.output_enabled,
        "pii_severity": policy.pii_severity,
        "injection_severity": policy.injection_severity,
        "forbidden_severity": policy.forbidden_severity,
        "output_pii_action": policy.output_pii_action,
        "input_rules": [
            "PII_RRN", "PII_PHONE", "PII_EMAIL", "PII_ACCOUNT",
            "PROMPT_INJECTION", "FORBIDDEN_CONTENT",
        ],
        "output_rules": [
            "PII_RRN", "PII_PHONE", "PII_EMAIL", "PII_ACCOUNT",
            "FORBIDDEN_CONTENT",
        ],
    })


@router.put("/admin/guardrails/policies")
async def update_guardrail_policies(request: Request, body: PolicyUpdateRequest):
    ctx = await context(request, write=True)
    if ctx.effective_role != "PADMIN":
        raise AppError("MANAGEMENT_DENIED", 403)
    updates = body.model_dump(exclude_unset=True, exclude={"expected_revision"})
    if not updates:
        raise AppError("REQUEST_INVALID", 422)

    pool = getattr(request.app.state, "pool", None)
    if pool is not None:
        repo = GuardrailRepository(pool)
        trace_id = getattr(request.state, "request_id", None)
        if trace_id is None or not isinstance(trace_id, UUID):
            trace_id = uuid4()
        updated = await repo.update_policy(
            ctx,
            trace_id=trace_id,
            expected_revision=body.expected_revision,
            policy_dict=updates
        )
        return response(request, {
            "revision": updated.get("revision"),
            "input_enabled": updated.get("input_enabled"),
            "output_enabled": updated.get("output_enabled"),
            "pii_severity": updated.get("pii_severity"),
            "injection_severity": updated.get("injection_severity"),
            "forbidden_severity": updated.get("forbidden_severity"),
            "output_pii_action": updated.get("output_pii_action"),
        })

    try:
        policy = update_policy(expected_revision=body.expected_revision, **updates)
    except ValueError:
        raise AppError("REVISION_CONFLICT", 409)
    return response(request, {
        "revision": policy.revision,
        "input_enabled": policy.input_enabled,
        "output_enabled": policy.output_enabled,
        "pii_severity": policy.pii_severity,
        "injection_severity": policy.injection_severity,
        "forbidden_severity": policy.forbidden_severity,
        "output_pii_action": policy.output_pii_action,
    })


@router.get("/admin/guardrails/violations")
async def get_violations(request: Request):
    ctx = await context(request)
    if ctx.effective_role != "PADMIN":
        raise AppError("MANAGEMENT_DENIED", 403)

    pool = getattr(request.app.state, "pool", None)
    if pool is not None:
        repo = GuardrailRepository(pool)
        data = await repo.list_violations(ctx)
        return response(request, {
            "items": data.get("items", []),
            "total_count": data.get("total_count", 0),
        })

    # Return most recent 50 violations for the tenant
    tenant_violations = [
        v for v in reversed(_VIOLATIONS)
        if v["tenant_id"] == str(ctx.tenant_id)
    ][:50]

    return response(request, {
        "items": tenant_violations,
        "total_count": len([
            v for v in _VIOLATIONS
            if v["tenant_id"] == str(ctx.tenant_id)
        ]),
    })
