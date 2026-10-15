import pytest
from uuid import uuid4
from datetime import datetime, timezone
from app.errors import AppError
from app.guardrails.repository import GuardrailRepository
from app.guardrails.engine import text_hash

@pytest.mark.anyio
async def test_guardrail_policy_persistence_and_cas(db_fixture):
    """PADMIN can read and update policy via CAS; USER is forbidden."""
    ctx_padmin = await db_fixture.context("P-A", "A")
    ctx_user = await db_fixture.context("A-U1", "A")
    repo = GuardrailRepository(db_fixture.pool)

    # 1. USER read is forbidden
    with pytest.raises(AppError) as exc_u:
        await repo.get_policy(ctx_user)
    assert exc_u.value.status == 403

    # 2. PADMIN reads default v1
    pol = await repo.get_policy(ctx_padmin)
    assert pol["revision"] == 1
    assert pol["input_enabled"] is True
    assert pol["output_pii_action"] == "mask"

    # 3. PADMIN updates policy (expected_revision = 1 -> new revision = 2)
    trace_id = uuid4()
    updated = await repo.update_policy(
        ctx_padmin,
        trace_id=trace_id,
        expected_revision=1,
        policy_dict={
            "input_enabled": True,
            "output_enabled": True,
            "pii_severity": "block",
            "injection_severity": "block",
            "forbidden_severity": "block",
            "output_pii_action": "block"
        }
    )
    assert updated["revision"] == 2
    assert updated["output_pii_action"] == "block"

    # 4. CAS Conflict: updating with stale expected_revision 1 fails with 409
    with pytest.raises(AppError) as exc_conflict:
        await repo.update_policy(
            ctx_padmin,
            trace_id=uuid4(),
            expected_revision=1,
            policy_dict={"output_pii_action": "mask"}
        )
    assert exc_conflict.value.status == 409

    # 5. Subsequent read returns revision 2
    pol2 = await repo.get_policy(ctx_padmin)
    assert pol2["revision"] == 2
    assert pol2["output_pii_action"] == "block"


@pytest.mark.anyio
async def test_guardrail_violation_persistence_and_isolation(db_fixture):
    """Violations are stored with content_hash (no raw text) and isolated between tenants."""
    ctx_a_padmin = await db_fixture.context("P-A", "A")
    ctx_a_user = await db_fixture.context("A-U1", "A")
    ctx_b_adm = await db_fixture.context("B-ADM", "B")

    repo = GuardrailRepository(db_fixture.pool)

    # 1. Record violation for Tenant A
    raw_text = "주민번호 900101-1234567 포함 테스트"
    c_hash = text_hash(raw_text)
    trace_id = uuid4()
    
    violation_id = await repo.record_violation(
        ctx_a_padmin,
        trace_id=trace_id,
        user_id=ctx_a_user.user_id,
        run_id=None,
        direction="input",
        rule_ids=["PII_RRN"],
        content_hash=c_hash,
        policy_revision=2
    )
    assert violation_id is not None

    # 2. Tenant A lists violations and sees the recorded entry
    list_a = await repo.list_violations(ctx_a_padmin)
    assert list_a["total_count"] >= 1
    items = list_a["items"]
    assert any(item["violation_id"] == str(violation_id) for item in items)
    matched = next(item for item in items if item["violation_id"] == str(violation_id))
    assert matched["content_hash"] == c_hash
    assert matched["rule_ids"] == ["PII_RRN"]
    # Verify raw text is NOT stored anywhere
    assert "900101-1234567" not in str(matched)

    # 3. Tenant B TADMIN cannot list PADMIN-level violations (RBAC 403)
    with pytest.raises(AppError) as exc_b:
        await repo.list_violations(ctx_b_adm)
    assert exc_b.value.status == 403

    # 4. Direct DML/SELECT on table is denied for ai_web (Security Definer pattern)
    from app.db import tenant_transaction
    import psycopg
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with tenant_transaction(db_fixture.pool, ctx_b_adm) as conn:
            await conn.execute("SELECT * FROM ops.guardrail_violations")
