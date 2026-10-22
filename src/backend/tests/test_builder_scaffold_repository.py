import asyncio
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.builder.scaffold_repository import ScaffoldRepository
from app.builder.scaffold_schemas import ScaffoldRequest


class _Cursor:
    def __init__(self, row):
        self.row = row

    async def fetchone(self):
        return self.row


class _Connection:
    def __init__(self):
        self.calls = []

    async def execute(self, query, args):
        self.calls.append((query, args))
        return _Cursor({"data": {"proposal_id": str(uuid4()), "state": "admitted", "replayed": False}})


def test_admit_uses_fixed_function_and_excludes_client_id_from_payload(monkeypatch):
    conn = _Connection()
    ctx = SimpleNamespace(session_id=uuid4(), tenant_id=uuid4())

    class _Transaction:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr("app.builder.scaffold_repository.tenant_transaction", lambda *_: _Transaction())
    request = ScaffoldRequest(
        client_request_id=uuid4(), target="agent", intent="심사 결과를 요약하는 Agent",
        answers={"audience": "담당자"}, document_refs=[],
    )
    repo = ScaffoldRepository(object())

    result = asyncio.run(repo.admit(
        ctx, request, model_id="gpt-4o-mini", policy_revision=4, budget_period=date(2026, 10, 1),
    ))

    sql, args = conn.calls[0]
    assert "security.builder_scaffold_admit" in sql
    assert args[:4] == (ctx.session_id, ctx.tenant_id, request.client_request_id, "agent")
    assert isinstance(args[4], Jsonb)
    assert args[4].obj == {
        "intent": "심사 결과를 요약하는 Agent",
        "answers": {"audience": "담당자"},
        "document_refs": [],
    }
    assert args[5:] == ("gpt-4o-mini", "4", date(2026, 10, 1))
    assert result["state"] == "admitted"
