import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from app.ai.gateway import AiGateway
from app.ai.types import ProviderOutcome
from app.ai.repository import ExecutionError
from app.execution.manager import ExecutionManager

class Repository:
    def __init__(self):
        self.call_id = uuid4()
        self.settled = []
    async def reserve(self, *args): return {"call_id": str(self.call_id), "created": True}
    async def dispatch(self, *args): return SimpleNamespace(call_id=self.call_id)
    async def settle(self, ticket, claim, receipt, status, invalid):
        self.settled.append((receipt, status, invalid))
        return {"conflict": False, "invalid": False, "overrun": False}

class Provider:
    def __init__(self, body): self.body = body
    async def generate(self, claim, messages, on_delta):
        cut = len(self.body)//2
        await on_delta(self.body[:cut])
        await on_delta(self.body[cut:])
        return ProviderOutcome(self.body, None, "unknown", None)

def ticket():
    return SimpleNamespace(messages=[], task_kind="chat", agent="general",
        run=SimpleNamespace(tenant_id=uuid4(), run_id=uuid4()),
        ctx=SimpleNamespace(user_id=uuid4()))

@pytest.mark.anyio
async def test_actual_gateway_never_forwards_uninspected_chunks():
    repo = Repository(); published = []
    async def publish(text): published.append(text)
    outcome = await AiGateway(repo, Provider("연락처 010-1234-5678")).execute(ticket(), publish)
    assert published == []
    assert "010-1234-5678" not in outcome.body
    assert len(repo.settled) == 1

@pytest.mark.anyio
async def test_gateway_enforces_utf8_bytes_and_still_settles():
    repo = Repository()
    outcome = await AiGateway(repo, Provider("가"*11000)).execute(ticket(), AsyncMock())
    assert outcome.body is None
    assert outcome.safe_error_code == "PAYLOAD_TOO_LARGE"
    assert len(repo.settled) == 1

@pytest.mark.anyio
@pytest.mark.parametrize("saved", [True, False, "storage-error"])
async def test_actual_manager_publishes_only_after_successful_finish(saved):
    t = ticket(); events = []
    class Repo:
        async def claim(self, *args): return t
        async def finish(self, *args):
            events.append("finish")
            if saved == "storage-error": raise ExecutionError("LEDGER_UNAVAILABLE")
            return saved
        async def fail(self, *args): events.append("fail")
    class Hub:
        def begin(self, *args): pass
        def append(self, *args): events.append("publish")
        def clear(self, *args): pass
    manager = ExecutionManager(Repo(), None, "mock", Hub())
    manager.gateway.execute = AsyncMock(return_value=ProviderOutcome("safe", None, "unknown", None))
    await manager._run(t.ctx, t.run.run_id)
    if saved is True:
        assert events == ["finish", "publish"]
    else:
        assert "publish" not in events
        assert "fail" in events

@pytest.mark.anyio
@pytest.mark.parametrize("body", [{"invalid":"body"}, "\ud800"])
async def test_invalid_final_output_still_reaches_settlement(body):
    repo=Repository()
    class RawProvider:
        async def generate(self,claim,messages,on_delta):
            return ProviderOutcome(body,None,"unknown",None)
    outcome=await AiGateway(repo,RawProvider()).execute(ticket(),AsyncMock())
    assert outcome.body is None
    assert outcome.safe_error_code=="OUTPUT_INVALID"
    assert len(repo.settled)==1
