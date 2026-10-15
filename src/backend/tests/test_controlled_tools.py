import pytest
from app.errors import AppError
from app.tools.registry import ToolRegistry
from app.tools.adapters import FixtureToolAdapter, RealInstitutionalToolAdapter

@pytest.mark.anyio
async def test_controlled_tools_strict_schema_and_execution():
    """T6a: Standard tools execute via fixture adapter with strict schema enforcement."""
    registry = ToolRegistry(adapter=FixtureToolAdapter())

    # 1. Normal invocation of financial_product_lookup
    res = await registry.invoke(
        "financial_product_lookup",
        {"category": "deposit", "query": "디지털"},
        client_request_id="req-1",
    )
    assert res["status"] == "success"
    items = res["result"]["items"]
    assert len(items) == 1
    assert items[0]["code"] == "DP-001"
    assert res["result"]["source"] == "fixture"

    # 2. Strict schema: Disallow additionalProperties
    with pytest.raises(AppError) as exc_extra:
        await registry.invoke(
            "financial_product_lookup",
            {"category": "deposit", "unauthorized_extra_field": "exploit"},
        )
    assert exc_extra.value.status == 422
    assert exc_extra.value.code == "TOOL_ARGUMENTS_INVALID"

    # 3. Enum constraint: Invalid category
    with pytest.raises(AppError) as exc_enum:
        await registry.invoke(
            "financial_product_lookup",
            {"category": "invalid_cryptocurrency"},
        )
    assert exc_enum.value.status == 422
    assert exc_enum.value.code == "TOOL_ARGUMENTS_INVALID"


@pytest.mark.anyio
async def test_controlled_tools_security_and_idempotency():
    """T6a: Disallow malicious SQL/URL/path patterns and enforce idempotency."""
    registry = ToolRegistry(adapter=FixtureToolAdapter())

    # 1. SQL injection keyword rejection
    with pytest.raises(AppError) as exc_sql:
        await registry.invoke(
            "kb_rule_query",
            {"keyword": "DROP TABLE users;"},
        )
    assert exc_sql.value.status == 422

    # 2. Path traversal rejection
    with pytest.raises(AppError) as exc_path:
        await registry.invoke(
            "kb_rule_query",
            {"keyword": "../../etc/passwd"},
        )
    assert exc_path.value.status == 422

    # 3. Arbitrary URL rejection
    with pytest.raises(AppError) as exc_url:
        await registry.invoke(
            "kb_rule_query",
            {"keyword": "http://malicious-site.com/payload"},
        )
    assert exc_url.value.status == 422

    # 4. Idempotency with client_request_id:
    # First call with req-idem succeeds
    await registry.invoke("kb_rule_query", {"section": "security"}, client_request_id="req-idem")
    # Same call with same args succeeds
    await registry.invoke("kb_rule_query", {"section": "security"}, client_request_id="req-idem")
    # Call with same client_request_id but different args fails with 409
    with pytest.raises(AppError) as exc_idem:
        await registry.invoke("kb_rule_query", {"section": "ai_governance"}, client_request_id="req-idem")
    assert exc_idem.value.status == 409


@pytest.mark.anyio
async def test_controlled_tools_real_adapter_requires_configuration():
    """T6a: Real institutional adapter must raise 409 FEATURE_NOT_READY when unconfigured."""
    real_registry = ToolRegistry(adapter=RealInstitutionalToolAdapter())

    with pytest.raises(AppError) as exc_real:
        await real_registry.invoke(
            "financial_product_lookup",
            {"category": "deposit"},
        )
    assert exc_real.value.status == 409
    assert exc_real.value.code == "FEATURE_NOT_READY"
