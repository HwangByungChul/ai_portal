"""Service boundary tests: proposals never invoke asset/conversation side effects."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.ai.gateway import AiGateway
from app.ai.types import DispatchClaim, ProviderOutcome, UsageReceipt
from app.builder.scaffold_schemas import ScaffoldRequest
from app.builder.scaffold_service import ScaffoldGenerationService


class _Guardrails:
    def __init__(self):
        self.inputs = []

    async def inspect(self, ctx, text, *, direction, trace_id=None, **kwargs):
        self.inputs.append((direction, text, trace_id))
        return SimpleNamespace(action="allow", masked_text=None, rule_ids=[], revision=4)

    async def snapshot(self, ctx):
        return SimpleNamespace(revision=4)


class _Repository:
    def __init__(self):
        self.completed = []
        self.failed = []

    async def complete(self, ctx, proposal_id, revision, payload):
        self.completed.append((ctx, proposal_id, revision, payload))
        return {"state": "ready", "proposal": payload}

    async def fail(self, ctx, proposal_id, revision, code):
        self.failed.append((ctx, proposal_id, revision, code))
        return {"state": "failed", "error_code": code}


class _Gateway:
    def __init__(self, outcome):
        self.outcome = outcome
        self.ticket = None

    async def execute(self, ticket, on_delta):
        self.ticket = ticket
        return self.outcome


class _Documents:
    async def allowed(self, ctx, refs, mode):
        return []


def _request():
    return ScaffoldRequest(client_request_id=uuid4(), target="agent", intent="검토용 업무 도우미")


def test_generation_stores_only_a_validated_gateway_proposal_without_other_side_effects():
    import json
    raw = {
        "config": {"name": "업무 도우미", "description": "검토용 초안", "instructions": "친절하게 답변하세요.", "execution_kind": "general"},
        "profile": {"schema_version": 1, "system_prompt": "친절하게 답변하세요.", "developer_prompt": "", "user_template": "{{question}}", "model_ref": "default_general", "document_refs": []},
        "missing_questions": [], "warnings": [],
    }
    repo = _Repository()
    guard = _Guardrails()
    gateway = _Gateway(ProviderOutcome(json.dumps(raw, ensure_ascii=False), None, "observed", None))
    svc = ScaffoldGenerationService(gateway, repo, guard, _Documents(), "mock")
    ctx, proposal_id, trace_id = SimpleNamespace(tenant_id=uuid4()), uuid4(), uuid4()
    result = asyncio.run(svc.generate(ctx, proposal_id, trace_id, 1, _request()))
    assert result["state"] == "ready"
    assert repo.completed[0][:3] == (ctx, proposal_id, 1)
    assert not repo.failed
    assert gateway.ticket.task_kind == "builder_scaffold"
    assert gateway.ticket.model_id == "gpt-4o-mini"
    assert gateway.ticket.run.run_id is None  # No synthetic persisted conversation/run.
    assert guard.inputs[0][0] == "input"


def test_gateway_failure_is_terminal_without_proposal_body():
    repo = _Repository()
    svc = ScaffoldGenerationService(
        _Gateway(ProviderOutcome(None, None, "unknown", "USAGE_INVALID")),
        repo, _Guardrails(), _Documents(), "mock",
    )
    ctx, proposal_id, trace_id = SimpleNamespace(tenant_id=uuid4()), uuid4(), uuid4()
    try:
        asyncio.run(svc.generate(ctx, proposal_id, trace_id, 1, _request()))
    except Exception as error:
        assert getattr(error, "code", None) == "USAGE_INVALID"
    else:
        raise AssertionError("failed metering must not return a proposal")
    assert repo.failed == [(ctx, proposal_id, 1, "USAGE_INVALID")]
    assert not repo.completed


class _MeteredRepository(_Repository):
    def __init__(self):
        super().__init__()
        self.settlements = []

    async def reserve(self, ticket, fingerprint):
        return {"call_id": str(uuid4()), "created": True}

    async def dispatch(self, ticket, call_id):
        return DispatchClaim(call_id, ticket.run.epoch, "private-claim")

    async def settle(self, ticket, claim, receipt, end_status, invalid=False):
        self.settlements.append((receipt, end_status, invalid))
        return {"conflict": False, "invalid": invalid, "overrun": False}

    async def release_unfired(self, ticket, call_id):
        return True


class _Provider:
    async def generate(self, claim, messages, on_delta):
        return ProviderOutcome("{}", UsageReceipt(2, 1, 3, "unknown-model", "default", None), "unknown", None)


def test_unknown_usage_is_settled_as_invalid_and_never_completes():
    repo = _MeteredRepository()
    gateway = AiGateway(repo, _Provider(), guardrails=_Guardrails())
    svc = ScaffoldGenerationService(gateway, repo, _Guardrails(), _Documents(), "mock")
    ctx, proposal_id, trace_id = SimpleNamespace(tenant_id=uuid4()), uuid4(), uuid4()
    try:
        asyncio.run(svc.generate(ctx, proposal_id, trace_id, 1, _request()))
    except Exception as error:
        assert getattr(error, "code", None) == "USAGE_INVALID"
    else:
        raise AssertionError("unrecognized usage cannot produce a ready proposal")
    assert repo.settlements == [(None, "unknown", True)]
    assert not repo.completed
    assert repo.failed[0][3] == "USAGE_INVALID"


def test_model_cannot_invent_document_refs_even_if_schema_is_valid():
    import json
    raw = {
        "config": {"name": "업무 도우미", "description": "검토용 초안", "instructions": "친절하게 답변하세요.", "execution_kind": "rules_rag"},
        "profile": {"schema_version": 1, "system_prompt": "친절하게 답변하세요.", "developer_prompt": "", "user_template": "{{question}}", "model_ref": "default_rules_rag", "document_refs": [{"document_id": str(uuid4()), "version_id": str(uuid4())}]},
        "missing_questions": [], "warnings": [],
    }
    repo = _Repository()
    svc = ScaffoldGenerationService(
        _Gateway(ProviderOutcome(json.dumps(raw), None, "observed", None)),
        repo, _Guardrails(), _Documents(), "mock",
    )
    ctx, proposal_id, trace_id = SimpleNamespace(tenant_id=uuid4()), uuid4(), uuid4()
    try:
        asyncio.run(svc.generate(ctx, proposal_id, trace_id, 1, _request()))
    except Exception as error:
        assert getattr(error, "code", None) == "SCAFFOLD_PROPOSAL_INVALID"
    else:
        raise AssertionError("provider-invented document refs must be rejected")
    assert not repo.completed
    assert repo.failed[0][3] == "SCAFFOLD_PROPOSAL_INVALID"


class _ObservedScaffoldProvider:
    async def generate(self, claim, messages, on_delta):
        import json
        payload = {
            "config": {"name": "업무 도우미", "description": "검토용 초안", "instructions": "친절하게 답변하세요.", "execution_kind": "general"},
            "profile": {"schema_version": 1, "system_prompt": "친절하게 답변하세요.", "developer_prompt": "", "user_template": "{{question}}", "model_ref": "default_general", "document_refs": []},
            "missing_questions": [], "warnings": [],
        }
        return ProviderOutcome(json.dumps(payload, ensure_ascii=False), UsageReceipt(20, 15, 35, "gpt-4o-mini", "default", None), "observed", None)


class _RevisionTrackingRepository(_MeteredRepository):
    def __init__(self):
        super().__init__()
        self.proposal_revision = 1

    async def reserve(self, ticket, fingerprint):
        self.proposal_revision += 1  # Mirrors reserve's admitted -> generating CAS.
        return await super().reserve(ticket, fingerprint)

    async def fail(self, ctx, proposal_id, revision, code):
        if revision < 1 or self.proposal_revision != revision + 1:
            raise AssertionError("failure must use the admitted revision and exact reserved successor")
        return await super().fail(ctx, proposal_id, revision, code)


def test_metered_reserve_settle_complete_keeps_original_revision_token():
    repo = _RevisionTrackingRepository()
    gateway = AiGateway(repo, _ObservedScaffoldProvider(), guardrails=_Guardrails())
    svc = ScaffoldGenerationService(gateway, repo, _Guardrails(), _Documents(), "mock")
    ctx, proposal_id, trace_id = SimpleNamespace(tenant_id=uuid4()), uuid4(), uuid4()
    result = asyncio.run(svc.generate(ctx, proposal_id, trace_id, 1, _request()))
    assert result["state"] == "ready"
    assert repo.proposal_revision == 2
    assert repo.completed[0][2] == 1
    assert len(repo.settlements) == 1 and repo.settlements[0][1] == "observed"


def test_metered_failure_uses_admission_revision_after_reserve_increment():
    repo = _RevisionTrackingRepository()
    gateway = AiGateway(repo, _Provider(), guardrails=_Guardrails())
    svc = ScaffoldGenerationService(gateway, repo, _Guardrails(), _Documents(), "mock")
    ctx, proposal_id, trace_id = SimpleNamespace(tenant_id=uuid4()), uuid4(), uuid4()
    try:
        asyncio.run(svc.generate(ctx, proposal_id, trace_id, 1, _request()))
    except Exception as error:
        assert getattr(error, "code", None) == "USAGE_INVALID"
    else:
        raise AssertionError("unknown usage must fail the proposal")
    assert repo.proposal_revision == 2
    assert repo.failed[0][2] == 1
    assert repo.settlements and repo.settlements[0][2] is True
