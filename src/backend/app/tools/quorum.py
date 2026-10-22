"""Quorum and dual-control approval policy for financial MCP tools (4-Eyes Principle).

Enforces:
- Self-approval prohibition: Requester cannot approve own requested tool.
- Duplicate approval prohibition: Same administrator cannot approve twice.
- Quorum rules:
  - 'read_only': 1 PADMIN approval required.
  - 'financial_side_effect': Minimum 2 distinct PADMIN approvals required.
  - 'unclassified': Approval blocked pending risk policy classification.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from app.errors import AppError


@dataclass(frozen=True)
class QuorumEvaluationResult:
    status: Literal["approved", "partially_approved", "rejected"]
    current_approvals: int
    required_quorum: int
    can_publish: bool
    approver_ids: list[str]


def evaluate_quorum(
    risk_class: str,
    prior_decisions: list[dict[str, Any]],
    requester_id: str,
    candidate_actor_id: str,
    action: Literal["approve", "reject"],
) -> QuorumEvaluationResult:
    """Evaluate whether candidate action complies with dual-control and quorum requirements."""
    # Self-approval block
    if candidate_actor_id == requester_id:
        raise AppError("APPROVAL_DENIED", 403)

    if action == "reject":
        return QuorumEvaluationResult(
            status="rejected",
            current_approvals=0,
            required_quorum=1,
            can_publish=False,
            approver_ids=[],
        )

    # Validate risk classification
    if risk_class == "unclassified":
        raise AppError("TOOL_RISK_UNCLASSIFIED", 400)

    required_quorum = 2 if risk_class == "financial_side_effect" else 1

    existing_approver_ids: set[str] = set()
    for decision in prior_decisions:
        if decision.get("action") == "approve":
            actor = str(decision.get("actor_id"))
            existing_approver_ids.add(actor)

    # Duplicate approval block
    if candidate_actor_id in existing_approver_ids:
        raise AppError("REVISION_CONFLICT", 409)

    existing_approver_ids.add(candidate_actor_id)
    current_count = len(existing_approver_ids)

    if current_count >= required_quorum:
        return QuorumEvaluationResult(
            status="approved",
            current_approvals=current_count,
            required_quorum=required_quorum,
            can_publish=True,
            approver_ids=sorted(existing_approver_ids),
        )

    return QuorumEvaluationResult(
        status="partially_approved",
        current_approvals=current_count,
        required_quorum=required_quorum,
        can_publish=False,
        approver_ids=sorted(existing_approver_ids),
    )
