import pytest
from types import SimpleNamespace
from uuid import uuid4
from app.guardrails.service import GuardrailService
from app.guardrails.repository import GuardrailRepository
from app.guardrails.engine import update_policy,get_policy
from app.errors import AppError

@pytest.mark.anyio
async def test_current_tenant_policy_reaches_engine_and_durable_audit(db_fixture):
    admin=await db_fixture.context("P-A","A")
    user=await db_fixture.context("A-U1","A")
    repo=GuardrailRepository(db_fixture.pool)
    initial=await repo.get_policy(admin)
    await repo.update_policy(admin,uuid4(),initial["revision"],{"output_pii_action":"block"})
    service=GuardrailService(repository=repo)
    result=await service.inspect(user,"연락처 010-1234-5678",direction="output")
    assert result.action=="block"
    history=await repo.list_violations(admin)
    assert any(row["user_id"]==str(user.user_id) and row["policy_revision"]==2 for row in history["items"])
    assert "010-1234-5678" not in str(history)
    # New service instance reads DB, not a stale process singleton.
    assert (await GuardrailService(db_fixture.pool).snapshot(user)).output_pii_action=="block"
    other=await db_fixture.context("B-U1","B")
    assert (await service.snapshot(other)).output_pii_action=="mask"

@pytest.mark.anyio
async def test_runtime_baseline_cannot_be_disabled_by_organization(db_fixture):
    admin=await db_fixture.context("P-A","A")
    user=await db_fixture.context("A-U1","A")
    repo=GuardrailRepository(db_fixture.pool)
    initial=await repo.get_policy(admin)
    await repo.update_policy(admin,uuid4(),initial["revision"],{"input_enabled":False,"output_enabled":False})
    service=GuardrailService(repository=repo)
    assert (await service.inspect(user,"연락처 010-1234-5678",direction="input")).action=="block"
    assert (await service.inspect(user,"연락처 010-1234-5678",direction="output")).action=="mask"

@pytest.mark.anyio
async def test_audit_failure_is_not_swallowed():
    class Repo:
        async def runtime_policy(self,ctx):return {"revision":3,"output_pii_action":"mask"}
        async def record_violation(self,*args,**kwargs):raise AppError("STORAGE_UNAVAILABLE",503)
    service=GuardrailService(repository=Repo())
    with pytest.raises(AppError):
        await service.inspect(SimpleNamespace(user_id=uuid4()),"연락처 010-1234-5678",direction="output")
