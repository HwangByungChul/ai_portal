"""Reserved namespace source/RPC contract only; migration is not executed here."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import re
from types import SimpleNamespace
from uuid import UUID

import psycopg
import pytest

from app.errors import AppError
from app.tools import dynamic_repository
from app.tools.registry import GLOBAL_TOOL_REGISTRY


MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def test_additive_trigger_reserves_exact_static_namespace_before_registry_writes():
    source = (MIGRATIONS / "064_mcp_tool_reserved_ids.sql").read_text()
    reserved = re.search(r"NEW\.tool_id IN \(([^)]+)\)", source).group(1)
    assert set(re.findall(r"'([^']+)'", reserved)) == {item["tool_id"] for item in GLOBAL_TOOL_REGISTRY.list_public()}
    assert "BEFORE INSERT OR UPDATE OF tool_id ON portal.mcp_tool_definitions" in source
    assert "FOR EACH ROW EXECUTE FUNCTION security.mcp_tool_reject_reserved_id()" in source
    assert "USING ERRCODE='A0422'" in source
    assert "OWNER TO ai_policy_executor" in source
    assert "SET search_path=pg_catalog,security,portal,pg_temp" in source
    assert "FROM PUBLIC,ai_web,ai_index,ai_meter" in source
    # The existing RPC still authorizes the session/tenant before its first write.
    rpc = (MIGRATIONS / "056_mcp_tool_registry_control.sql").read_text()
    assert rpc.index("security.operations_authorize(p_session,p_tenant,'agent_admin',p_action='register')") < rpc.index("INSERT INTO portal.mcp_tool_definitions")
    assert not re.search(r"\b(?:INSERT INTO|UPDATE portal|DELETE FROM|ALTER TABLE|DROP)\b", source)


class InvalidRegistration(psycopg.Error):
    sqlstate = "A0422"


@pytest.mark.parametrize("tool_id", ["financial_product_lookup", "kb_rule_query", "data_view_reader"])
def test_registration_uses_tenant_rpc_and_translates_reserved_id_rejection(monkeypatch, tool_id):
    ctx = SimpleNamespace(session_id=UUID(int=1), tenant_id=UUID(int=2))
    pool = object()
    calls = []

    class Connection:
        async def execute(self, query, parameters):
            calls.append((query, parameters))
            raise InvalidRegistration("ARGUMENT_REJECTED")

    @asynccontextmanager
    async def transaction(actual_pool, actual_ctx):
        assert actual_pool is pool and actual_ctx is ctx
        yield Connection()

    monkeypatch.setattr(dynamic_repository, "tenant_transaction", transaction)
    with pytest.raises(AppError) as caught:
        asyncio.run(dynamic_repository.DynamicToolRepository(pool).register(
            ctx, tool_id=tool_id, name="Fixture", description="collision", source_type="openapi",
            input_schema={}, raw_meta={}, dev_profile={}, prd_profile={},
        ))
    assert (caught.value.code, caught.value.status) == ("REQUEST_INVALID", 422)
    assert len(calls) == 1
    assert "security.mcp_tool_registry_control(" in calls[0][0]
    assert "'register'" in calls[0][0]
    assert calls[0][1][:3] == (ctx.session_id, ctx.tenant_id, tool_id)
