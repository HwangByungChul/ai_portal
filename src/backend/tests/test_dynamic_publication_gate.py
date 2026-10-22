from copy import deepcopy

from app.tools.publication_gate import publication_gate


def descriptor():
    return {
        "tool_id": "credit_check",
        "revision_number": 3,
        "digest": "a" * 64,
        "risk_policy_id": "dynamic-default-v1",
        "risk_policy_revision": 1,
        "approval_scope": "registration_review_only",
    }


def test_matching_snapshots_are_still_blocked_from_publication_and_execution():
    result = publication_gate(descriptor(), descriptor())

    assert result["snapshot_matches"] is True
    assert result["publishable"] is False
    assert result["execution_ready"] is False
    assert "EXACT_REVISION_APPROVAL_GATE_NOT_IMPLEMENTED" in result["blockers"]


def test_registry_revision_and_digest_changes_are_reported():
    submitted = descriptor()
    current = descriptor()
    current["revision_number"] += 1
    current["digest"] = "b" * 64

    result = publication_gate(submitted, current)

    assert result["snapshot_matches"] is False
    assert "REGISTRY_REVISION_MISMATCH" in result["blockers"]
    assert "REGISTRY_DIGEST_MISMATCH" in result["blockers"]


def test_changed_risk_policy_is_reported():
    submitted = descriptor()
    current = descriptor()
    current["risk_policy_revision"] += 1

    result = publication_gate(submitted, current)

    assert result["snapshot_matches"] is False
    assert "RISK_POLICY_MISMATCH" in result["blockers"]


def test_missing_or_malformed_descriptor_fails_closed():
    for malformed in (None, {}, {**descriptor(), "digest": "not-a-digest"}):
        result = publication_gate(malformed, descriptor())
        assert result["snapshot_matches"] is False
        assert result["publishable"] is False
        assert result["execution_ready"] is False
        assert "DESCRIPTOR_MISSING_OR_MALFORMED" in result["blockers"]


def test_client_authority_fields_cannot_make_matching_snapshot_publishable():
    client_influenced = deepcopy(descriptor()) | {
        "publication_status": "approved_published",
        "target_environment": "production",
        "mfa_verified": True,
        "execution_ready": True,
    }

    result = publication_gate(client_influenced, descriptor())

    assert result["snapshot_matches"] is True
    assert result["publishable"] is False
    assert result["execution_ready"] is False
    assert "EXACT_REVISION_APPROVAL_GATE_NOT_IMPLEMENTED" in result["blockers"]


def test_exact_gate_enabled_grants_publishable():
    result = publication_gate(
        descriptor(),
        descriptor(),
        exact_gate_enabled=True,
    )
    assert result["snapshot_matches"] is True
    assert result["publishable"] is True
    assert result["execution_ready"] is False
    assert len(result["blockers"]) == 0


def test_exact_gate_enabled_with_active_publication_grants_execution_ready():
    result = publication_gate(
        descriptor(),
        descriptor(),
        exact_gate_enabled=True,
        has_active_publication=True,
    )
    assert result["publishable"] is True
    assert result["execution_ready"] is True
    assert len(result["blockers"]) == 0


def test_exact_gate_retired_blocks_publication():
    result = publication_gate(
        descriptor(),
        descriptor(),
        exact_gate_enabled=True,
        has_active_publication=True,
        is_retired=True,
    )
    assert result["publishable"] is False
    assert result["execution_ready"] is False
    assert "PUBLICATION_RETIRED" in result["blockers"]

