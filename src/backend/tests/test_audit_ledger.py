"""Unit and integrity tests for AuditLedgerService."""
import hashlib
import pytest
from app.tools.audit import AuditEvent, AuditLedgerService


@pytest.mark.anyio
async def test_audit_append_and_chain_verification():
    service = AuditLedgerService()
    tenant_id = "11111111-1111-1111-1111-111111111111"
    actor_id = "22222222-2222-2222-2222-222222222222"
    trace_id = "trace-abc-123"

    evt1 = await service.append(
        tenant_id=tenant_id,
        actor_id=actor_id,
        trace_id=trace_id,
        tool_id="credit_lookup",
        event_type="invocation",
        argument_digest=hashlib.sha256(b'{"user_id": "u1"}').hexdigest(),
    )
    assert len(evt1.chain_hash) == 64

    evt2 = await service.append(
        tenant_id=tenant_id,
        actor_id=actor_id,
        trace_id=trace_id,
        tool_id="credit_lookup",
        event_type="result",
        argument_digest=evt1.argument_digest,
        response_digest=hashlib.sha256(b'{"score": 850}').hexdigest(),
        duration_ms=45,
        status="success",
    )
    assert len(evt2.chain_hash) == 64
    assert evt2.chain_hash != evt1.chain_hash

    is_valid, corrupted_idx = service.verify_chain(tenant_id)
    assert is_valid is True
    assert corrupted_idx is None


@pytest.mark.anyio
async def test_audit_chain_tamper_detection():
    service = AuditLedgerService()
    tenant_id = "33333333-3333-3333-3333-333333333333"
    actor_id = "44444444-4444-4444-4444-444444444444"

    for i in range(5):
        await service.append(
            tenant_id=tenant_id,
            actor_id=actor_id,
            trace_id=f"trace-{i}",
            tool_id="account_inquiry",
            event_type="invocation",
            argument_digest=hashlib.sha256(str(i).encode()).hexdigest(),
        )

    assert service.verify_chain(tenant_id)[0] is True

    # Tamper with event at index 2
    chain = service._memory_ledger[tenant_id]
    original = chain[2]
    tampered = AuditEvent(
        event_id=original.event_id,
        tenant_id=original.tenant_id,
        tool_id="tampered_tool",  # modified field
        version_id=original.version_id,
        revision_number=original.revision_number,
        actor_id=original.actor_id,
        trace_id=original.trace_id,
        event_type=original.event_type,
        credential_ref_id=original.credential_ref_id,
        argument_digest=original.argument_digest,
        response_digest=original.response_digest,
        duration_ms=original.duration_ms,
        status=original.status,
        error_code=original.error_code,
        chain_hash=original.chain_hash,
        created_at=original.created_at,
    )
    chain[2] = tampered

    is_valid, corrupted_idx = service.verify_chain(tenant_id)
    assert is_valid is False
    assert corrupted_idx == 2


@pytest.mark.anyio
async def test_audit_filtering():
    service = AuditLedgerService()
    tenant_id = "55555555-5555-5555-5555-555555555555"
    actor_id = "66666666-6666-6666-6666-666666666666"

    await service.append(tenant_id, actor_id, "tr-1", "tool_a", "invocation", "dig1")
    await service.append(tenant_id, actor_id, "tr-2", "tool_b", "rate_limit", "dig2", status="blocked")
    await service.append(tenant_id, actor_id, "tr-1", "tool_a", "result", "dig1", status="success")

    filtered_trace = service.get_events(tenant_id, trace_id="tr-1")
    assert len(filtered_trace) == 2

    filtered_blocked = service.get_events(tenant_id, event_type="rate_limit")
    assert len(filtered_blocked) == 1
    assert filtered_blocked[0].tool_id == "tool_b"
