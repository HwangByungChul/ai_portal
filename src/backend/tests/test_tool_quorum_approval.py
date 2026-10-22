"""Unit tests for Quorum and dual-control approval policies."""
import pytest
from app.errors import AppError
from app.tools.quorum import evaluate_quorum


def test_quorum_self_approval_blocked():
    requester = "user-100"
    with pytest.raises(AppError) as exc_info:
        evaluate_quorum(
            risk_class="financial_side_effect",
            prior_decisions=[],
            requester_id=requester,
            candidate_actor_id=requester,
            action="approve",
        )
    assert exc_info.value.code == "APPROVAL_DENIED"
    assert exc_info.value.status == 403


def test_quorum_duplicate_approval_blocked():
    requester = "user-100"
    admin_1 = "admin-1"
    prior = [{"actor_id": admin_1, "action": "approve"}]

    with pytest.raises(AppError) as exc_info:
        evaluate_quorum(
            risk_class="financial_side_effect",
            prior_decisions=prior,
            requester_id=requester,
            candidate_actor_id=admin_1,
            action="approve",
        )
    assert exc_info.value.code == "REVISION_CONFLICT"
    assert exc_info.value.status == 409


def test_quorum_read_only_single_approval_succeeds():
    requester = "user-100"
    admin_1 = "admin-1"

    res = evaluate_quorum(
        risk_class="read_only",
        prior_decisions=[],
        requester_id=requester,
        candidate_actor_id=admin_1,
        action="approve",
    )
    assert res.status == "approved"
    assert res.current_approvals == 1
    assert res.required_quorum == 1
    assert res.can_publish is True
    assert res.approver_ids == [admin_1]


def test_quorum_financial_side_effect_dual_control():
    requester = "user-100"
    admin_1 = "admin-1"
    admin_2 = "admin-2"

    # Step 1: 1st approval -> partially_approved
    res_1 = evaluate_quorum(
        risk_class="financial_side_effect",
        prior_decisions=[],
        requester_id=requester,
        candidate_actor_id=admin_1,
        action="approve",
    )
    assert res_1.status == "partially_approved"
    assert res_1.current_approvals == 1
    assert res_1.required_quorum == 2
    assert res_1.can_publish is False

    # Step 2: 2nd distinct PADMIN approval -> approved
    prior = [{"actor_id": admin_1, "action": "approve"}]
    res_2 = evaluate_quorum(
        risk_class="financial_side_effect",
        prior_decisions=prior,
        requester_id=requester,
        candidate_actor_id=admin_2,
        action="approve",
    )
    assert res_2.status == "approved"
    assert res_2.current_approvals == 2
    assert res_2.required_quorum == 2
    assert res_2.can_publish is True
    assert res_2.approver_ids == [admin_1, admin_2]


def test_quorum_unclassified_risk_blocked():
    with pytest.raises(AppError) as exc_info:
        evaluate_quorum(
            risk_class="unclassified",
            prior_decisions=[],
            requester_id="user-1",
            candidate_actor_id="admin-1",
            action="approve",
        )
    assert exc_info.value.code == "TOOL_RISK_UNCLASSIFIED"


def test_quorum_rejection_immediately_terminates():
    res = evaluate_quorum(
        risk_class="financial_side_effect",
        prior_decisions=[{"actor_id": "admin-1", "action": "approve"}],
        requester_id="user-1",
        candidate_actor_id="admin-2",
        action="reject",
    )
    assert res.status == "rejected"
    assert res.can_publish is False
