"""Acceptance tests for DP11-DP13: Agent Builder Multi-Model Integration."""
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from app.builder.schemas import Profile, SaveProfile
from app.assets.routes import AssetConfig
from app.ai.model_registry import GLOBAL_REGISTRY, DEFAULT_MODEL_ID, APPROVED_MODELS
from app.builder.model_contracts import contract
from app.builder.execution import TrialExecutor
from app.ai.repository import RunTicket, VerifiedRun


def test_builder_profile_validation_approved_models():
    # Case C01: Approved models pass validation
    p1 = Profile(
        schema_version=1,
        system_prompt="지시문",
        developer_prompt="",
        user_template="{{question}}",
        model_ref="gpt-4o",
        document_refs=[],
    )
    assert p1.model_ref == "gpt-4o"

    p2 = Profile(
        schema_version=1,
        system_prompt="지시문",
        developer_prompt="",
        user_template="{{question}}",
        model_ref="mock-fast",
        document_refs=[],
    )
    assert p2.model_ref == "mock-fast"


def test_builder_profile_validation_rejects_unapproved_or_disabled():
    # Case C02: Unapproved model rejected
    with pytest.raises(ValueError, match="PROFILE_INVALID"):
        Profile(
            schema_version=1,
            system_prompt="지시문",
            developer_prompt="",
            user_template="{{question}}",
            model_ref="unknown-model-xyz",
            document_refs=[],
        )

    # Disabled model rejected
    with pytest.raises(ValueError, match="PROFILE_INVALID"):
        Profile(
            schema_version=1,
            system_prompt="지시문",
            developer_prompt="",
            user_template="{{question}}",
            model_ref="mock-disabled",
            document_refs=[],
        )


def test_save_profile_capability_matching():
    # Case C03: capability matching with execution_kind
    cfg_gen = AssetConfig(
        name="일반 에이전트",
        description="설명",
        instructions="일반 지시문",
        execution_kind="general",
    )
    # Valid general save with gpt-4o
    p_gen = Profile(
        schema_version=1,
        system_prompt="일반 지시문",
        developer_prompt="",
        user_template="{{question}}",
        model_ref="gpt-4o",
        document_refs=[],
    )
    sp = SaveProfile(
        client_request_id=uuid4(),
        config=cfg_gen,
        profile=p_gen,
    )
    assert sp.profile.model_ref == "gpt-4o"


def test_legacy_alias_fallback_in_registry():
    # Case C04: Legacy default aliases resolve to DEFAULT_MODEL_ID
    m_gen = GLOBAL_REGISTRY.resolve("default_general")
    assert m_gen.model_id == DEFAULT_MODEL_ID
    assert m_gen.enabled is True

    m_rag = GLOBAL_REGISTRY.resolve("default_rules_rag")
    assert m_rag.model_id == DEFAULT_MODEL_ID

    m_none = GLOBAL_REGISTRY.resolve(None)
    assert m_none.model_id == DEFAULT_MODEL_ID


def test_builder_model_contract_resolution():
    # Case C05: contract correctly maps model_ref
    c_gpt4o = contract("gpt-4o")
    assert c_gpt4o["model_ref"] == "gpt-4o"
    assert c_gpt4o["generation_model"] == "gpt-4o"
    assert c_gpt4o["price_version"] == APPROVED_MODELS["gpt-4o"].pricing_version
    assert c_gpt4o["max_completion_tokens"] > 0

    c_legacy = contract("default_general")
    assert c_legacy["model_ref"] == "default_general"


@pytest.mark.anyio
async def test_trial_executor_binds_model_id():
    # Case C06: TrialExecutor binds ticket.model_id from saved profile
    repo = MagicMock()
    repo.web_pool = MagicMock()
    gateway = MagicMock()
    gateway.execute = AsyncMock(return_value=MagicMock(safe_error_code=None, body="테스트 응답"))
    rag = None

    executor = TrialExecutor(repo, gateway, rag)

    # Mock TrialRepository read to return model_ref = 'gpt-4o'
    read_mock = AsyncMock(return_value={
        "run_id": str(uuid4()),
        "model_ref": "gpt-4o",
        "purpose": "generate",
    })
    
    from app.ai.repository import RunTicket, VerifiedRun
    v = VerifiedRun(uuid4(), uuid4(), uuid4(), uuid4(), 1, 1, 'mock')
    ticket = RunTicket(ctx=MagicMock(), run=v, worker="worker", messages=[], agent="general", task_kind="builder_trial")

    with pytest.MonkeyPatch.context() as mp:
        from app.builder.trials import TrialRepository
        mp.setattr(TrialRepository, "read", lambda self, ctx, run_id: read_mock())
        result = await executor.execute(ticket)

    passed_ticket = gateway.execute.call_args[0][0]
    assert passed_ticket.model_id == "gpt-4o"
    assert result["text"] == "테스트 응답"
    assert gateway.execute.called
