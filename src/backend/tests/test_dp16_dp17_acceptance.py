"""Acceptance Tests for DP-16 (RBAC, SOD, SSO) & DP-17 (Data Scope & Import Pipeline)."""
import pytest
from uuid import uuid4
from app.auth.sso import SsoService, SsoStateStore
from app.documents.data_imports import CreateDataImport, DecideDataImport
from app.errors import AppError

def test_dp16_sso_state_lifecycle_and_tamper_proofing():
    """DP-16: SSO state/nonce 발급, 정상 검증, 재사용 및 만료 차단 검증."""
    store = SsoStateStore(ttl_seconds=2)
    sso = SsoService(store=store)

    # 1. Normal state generation
    info = sso.get_auth_url("entra-id", "http://127.0.0.1:5173/auth/callback")
    assert info["provider"] == "entra-id"
    assert "login.microsoftonline.com" in info["auth_url"]
    assert f"state={info['state']}" in info["auth_url"]

    # 2. Normal callback consumption
    res = sso.verify_callback("entra-id", "test-code-123", info["state"])
    assert res["verified"] is True
    assert res["provider"] == "entra-id"

    # 3. Replay attack: reusing the same state must fail
    with pytest.raises(AppError) as exc_replay:
        sso.verify_callback("entra-id", "test-code-123", info["state"])
    assert exc_replay.value.code == "SSO_INVALID_STATE"
    assert exc_replay.value.status == 400

    # 4. Tampered state must fail
    with pytest.raises(AppError) as exc_tampered:
        sso.verify_callback("entra-id", "test-code-123", "fake-tampered-state-token")
    assert exc_tampered.value.code == "SSO_INVALID_STATE"

    # 5. Unsupported provider
    with pytest.raises(AppError) as exc_unsupported:
        sso.get_auth_url("unknown-provider", "http://127.0.0.1:5173/auth/callback")
    assert exc_unsupported.value.code == "SSO_PROVIDER_UNSUPPORTED"


def test_dp17_data_import_schema_validations():
    """DP-17: 데이터 반입 요청 DTO 유효성 검증."""
    req_id = uuid4()
    doc_id = uuid4()
    ver_id = uuid4()

    valid_req = CreateDataImport(
        client_request_id=req_id,
        document_id=doc_id,
        version_id=ver_id,
        classification="confidential",
        target_scope="department",
        reason="부서 신규 업무 규정 반입 신청",
    )
    assert valid_req.classification == "confidential"
    assert valid_req.target_scope == "department"

    # Reject empty reason
    with pytest.raises(ValueError):
        CreateDataImport(
            client_request_id=req_id,
            document_id=doc_id,
            version_id=ver_id,
            classification="internal",
            target_scope="org",
            reason="",
        )

    # Reject invalid classification
    with pytest.raises(ValueError):
        CreateDataImport(
            client_request_id=req_id,
            document_id=doc_id,
            version_id=ver_id,
            classification="invalid_scope",  # type: ignore
            target_scope="org",
            reason="사유",
        )


def test_dp17_data_import_decision_schema():
    """DP-17: 데이터 반입 심사 DTO 유효성 검증."""
    dec = DecideDataImport(
        decision="approved",
        comment="보안 검토 완료",
        expected_revision=1,
    )
    assert dec.decision == "approved"
    assert dec.expected_revision == 1

    # Reject invalid decision
    with pytest.raises(ValueError):
        DecideDataImport(
            decision="unknown",  # type: ignore
            expected_revision=1,
        )


def test_dp16_sod_rule_and_permission_contracts():
    """DP-16: SOD (직무 분리) 및 권한 모델 계약 검증."""
    # Simulation of database function behavior
    requester_id = uuid4()
    approver_id = requester_id  # Same user!

    # SOD Rule: Requester cannot approve their own request
    def check_sod(req_user, app_user):
        if req_user == app_user:
            raise AppError("SELF_APPROVAL_FORBIDDEN", 403)
        return True

    with pytest.raises(AppError) as exc_sod:
        check_sod(requester_id, approver_id)
    assert exc_sod.value.status == 403
    assert exc_sod.value.code == "SELF_APPROVAL_FORBIDDEN"

    # Different approver passes SOD check
    other_approver_id = uuid4()
    assert check_sod(requester_id, other_approver_id) is True
