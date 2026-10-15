from uuid import uuid4
import pytest
from app.errors import AppError
from app.use_cases.catalog import get_use_cases, get_use_case
from app.use_cases.routes import execute_use_case, ExecuteUseCaseRequest

def make_dummy_request(execution_enabled: bool = True):
    class DummySettings:
        pass
    settings = DummySettings()
    settings.execution_enabled = execution_enabled

    class DummyAppState:
        pass
    app_state = DummyAppState()
    app_state.settings = settings

    class DummyApp:
        pass
    app_obj = DummyApp()
    app_obj.state = app_state

    class DummyState:
        request_id = "test-req-id"

    class DummyRequest:
        app = app_obj
        state = DummyState()

    return DummyRequest()


@pytest.fixture
def mock_auth_context(monkeypatch):
    class MockCtx:
        user_id = "u1"
        tenant_id = "t1"
        effective_role = "USER"
    async def _mock_context(*args, **kwargs):
        return MockCtx()
    monkeypatch.setattr("app.use_cases.routes.context", _mock_context)


@pytest.mark.anyio
async def test_all_10_business_agents_catalog():
    """T6c: Exactly 10 standard business use case agents are defined with strict contracts."""
    agents = get_use_cases()
    assert len(agents) == 10
    agent_ids = [a.use_case_id for a in agents]
    expected_ids = [f"AGENT_{i:02d}" for i in range(1, 11)]
    assert agent_ids == expected_ids

    # Financial / decision agents MUST prohibit auto decisions
    for ucid in ["AGENT_05", "AGENT_06", "AGENT_08", "AGENT_09"]:
        agent = get_use_case(ucid)
        assert agent is not None
        assert agent.auto_decision_prohibited is True
        assert agent.disclaimer is not None and len(agent.disclaimer) > 0


@pytest.mark.anyio
@pytest.mark.parametrize("agent_id,prompt",[("AGENT_01","규정"),("AGENT_08","검토 안내")])
async def test_use_case_requires_controlled_runtime(mock_auth_context,agent_id,prompt):
    with pytest.raises(AppError) as caught:
        await execute_use_case(make_dummy_request(),agent_id,ExecuteUseCaseRequest(client_request_id=uuid4(),prompt=prompt))
    assert caught.value.code=="EXECUTION_NOT_READY"

@pytest.mark.anyio
async def test_use_case_runtime_guardrail_input_blocking(mock_auth_context):
    """T6c: Business agent rejects input containing PII or injection."""
    req = make_dummy_request(execution_enabled=True)
    # RRN pattern
    body = ExecuteUseCaseRequest(client_request_id=uuid4(),prompt="주민번호 900101-1234567에 대한 심사 부탁합니다.")

    with pytest.raises(AppError) as exc:
        await execute_use_case(req, "AGENT_08", body)
    assert exc.value.status == 422
    assert exc.value.code == "GUARDRAIL_INPUT_BLOCKED"


@pytest.mark.anyio
async def test_use_case_runtime_execution_not_ready(mock_auth_context):
    """T6c: Returns 409 EXECUTION_NOT_READY when execution_enabled is false."""
    req = make_dummy_request(execution_enabled=False)
    body = ExecuteUseCaseRequest(client_request_id=uuid4(),prompt="일반 질문")

    with pytest.raises(AppError) as exc:
        await execute_use_case(req, "AGENT_01", body)
    assert exc.value.status == 409
    assert exc.value.code == "EXECUTION_NOT_READY"
