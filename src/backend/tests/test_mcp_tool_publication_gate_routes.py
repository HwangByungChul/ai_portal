"""Database-free response contract for the tool approval detail route."""

import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from uuid import UUID

from app.tools import routes


REQUEST_ID = UUID("11111111-1111-4111-8111-111111111111")


def dynamic_descriptor():
    return {
        "tool_id": "credit_check",
        "revision_number": 3,
        "digest": "a" * 64,
        "risk_policy_id": "dynamic-default-v1",
        "risk_policy_revision": 1,
        "approval_scope": "registration_review_only",
    }


def detail_payload(descriptor):
    return {
        "request": {
            "request_id": str(REQUEST_ID),
            "tool_id": descriptor["tool_id"],
            "descriptor": deepcopy(descriptor),
            "status": "pending",
        },
        "current_head": None,
        "can_approve": True,
        "can_reject": True,
        "can_revoke": False,
        "validation": {"valid": True, "checks": []},
        "history": [],
        "diff": {"baseline_available": False},
    }


def call_detail(monkeypatch, submitted, current):
    payload = detail_payload(submitted)
    ctx = object()
    repository = object()
    service = SimpleNamespace(repository=repository)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(
            tool_control=service, settings=SimpleNamespace(mode="mock"),
        )),
        query_params={},
        state=SimpleNamespace(request_id="route-contract", tenant_id="tenant-a"),
    )

    async def fake_context(actual_request):
        assert actual_request is request
        return ctx

    class FakeReviewRepository:
        def __init__(self, actual_repository, kind, mode):
            assert actual_repository is repository
            assert (kind, mode) == ("tool", "mock")

        async def detail(self, actual_ctx, request_id):
            assert actual_ctx is ctx
            assert request_id == REQUEST_ID
            return deepcopy(payload)

    async def fake_current_descriptor(actual_request, actual_ctx, actual_service, tool_id):
        assert actual_request is request
        assert actual_ctx is ctx
        assert actual_service is service
        assert tool_id == submitted["tool_id"]
        return deepcopy(current)

    monkeypatch.setattr(routes, "context", fake_context)
    monkeypatch.setattr(routes, "ReviewRepository", FakeReviewRepository)
    monkeypatch.setattr(routes, "_current_descriptor", fake_current_descriptor)

    result = asyncio.run(routes.tool_detail(request, REQUEST_ID))
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    envelope = json.loads(result.body)
    assert envelope["meta"]["request_id"] == "route-contract"
    assert envelope["meta"]["tenant_id"] == "tenant-a"
    return envelope["data"], payload


def test_matching_dynamic_detail_still_denies_publication_and_execution(monkeypatch):
    descriptor = dynamic_descriptor()

    data, _ = call_detail(monkeypatch, descriptor, descriptor)

    assert data["publication_gate"] == {
        "snapshot_matches": True,
        "publishable": False,
        "execution_ready": False,
        "blockers": ["EXACT_REVISION_APPROVAL_GATE_NOT_IMPLEMENTED"],
    }
    assert data["can_approve"] is False
    assert data["validation"]["valid"] is False
    assert [check["code"] for check in data["validation"]["checks"]] == [
        "DYNAMIC_REGISTRATION_REVIEW_ONLY",
    ]


def test_mismatched_dynamic_detail_exposes_stable_snapshot_blocker(monkeypatch):
    submitted = dynamic_descriptor()
    current = {**submitted, "revision_number": 4}

    data, _ = call_detail(monkeypatch, submitted, current)

    assert data["publication_gate"] == {
        "snapshot_matches": False,
        "publishable": False,
        "execution_ready": False,
        "blockers": [
            "EXACT_REVISION_APPROVAL_GATE_NOT_IMPLEMENTED",
            "EXACT_REVISION_SNAPSHOT_MISMATCH",
            "REGISTRY_REVISION_MISMATCH",
        ],
    }
    assert data["can_approve"] is False
    assert data["validation"]["valid"] is False
    assert [check["code"] for check in data["validation"]["checks"]] == [
        "DESCRIPTOR_CHANGED", "DYNAMIC_REGISTRATION_REVIEW_ONLY",
    ]


def test_static_detail_preserves_existing_fields_without_publication_gate(monkeypatch):
    descriptor = {"tool_id": "data_view_reader", "version": "1"}

    data, original = call_detail(monkeypatch, descriptor, descriptor)

    assert "publication_gate" not in data
    assert data == original
