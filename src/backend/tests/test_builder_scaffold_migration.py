"""Static safety contract for the additive Builder call capability."""
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def test_builder_calls_reuse_call_attempts_and_call_meter_without_conversation_rows():
    sql = (MIGRATIONS / "069_builder_scaffold_shared_meter.sql").read_text(encoding="utf-8")
    assert "ALTER TABLE ops.call_attempts ADD COLUMN proposal_id uuid" in sql
    assert "run_id IS NULL AND job_id IS NULL AND proposal_id IS NOT NULL AND operation='builder_scaffold'" in sql
    assert "CREATE UNIQUE INDEX call_attempts_builder_scaffold_once" in sql
    assert "INSERT INTO ops.usage_events" in sql
    assert "security.call_release_internal" in sql
    assert "portal.messages" not in sql
    assert "CREATE TABLE" not in sql


def test_scaffold_permit_and_terminal_success_require_current_owner_valid_settlement():
    sql = (MIGRATIONS / "069_builder_scaffold_shared_meter.sql").read_text(encoding="utf-8")
    assert "q.execution_worker_hash IS DISTINCT FROM p_worker" in sql
    assert "security.operations_authorize(p_session,p_tenant,'agent_admin',true)" in sql
    assert "security.guardrail_runtime_policy" in sql
    assert "c.state<>'settled' OR c.provider_end_status<>'observed' OR c.usage_snapshot IS NULL OR c.cost_overrun" in sql
    assert "state='failed',request_payload='{}'::jsonb,proposal_payload=NULL" in sql
    assert "GRANT SELECT ON portal.builder_scaffold_proposals TO ai_policy_executor" in sql
    assert "GRANT SELECT ON portal.builder_scaffold_proposals TO ai_web" not in sql


def test_disposable_clone_harness_requires_explicit_builder_clone_dsn():
    script = (Path(__file__).resolve().parent.parent / "scripts" / "verify_builder_scaffold_clone.py").read_text(encoding="utf-8")
    assert "AI_BUILDER_DISPOSABLE_CLONE_DSN" in script
    assert "DISPOSABLE_BUILDER_CLONE_NAME_REQUIRED" in script
    assert "conn.rollback()" in script
    assert 'os.getenv("DATABASE_URL")' not in script


def test_owner_and_tenant_fences_and_terminal_failure_receipt_are_encoded():
    sql = (MIGRATIONS / "069_builder_scaffold_shared_meter.sql").read_text(encoding="utf-8")
    assert "WHERE tenant_id=p_tenant AND owner_user_id=u AND proposal_id=p_proposal" in sql
    assert "security.operations_authorize(p_session,p_tenant,'agent_admin',true)" in sql
    assert "role_name NOT IN ('TADMIN','PADMIN')" in sql
    assert "builder.scaffold_failed" in sql
    assert "proposal_payload=NULL" in sql
    assert "'usage',c.usage_snapshot-ARRAY['provider_request_id']::text[]" in sql
    assert "GRANT SELECT,INSERT,UPDATE ON portal.builder_scaffold_proposals TO ai_web" not in sql


def test_069_preserves_existing_operation_parent_and_typed_usage_contracts():
    sql = (MIGRATIONS / "069_builder_scaffold_shared_meter.sql").read_text(encoding="utf-8")
    assert "operation IN ('generate_general','generate_rag','embed_query','embed_document','builder_scaffold')" in sql
    assert "ALTER TABLE ops.call_attempts DROP CONSTRAINT call_parent_kind" in sql
    assert "operation='generate_general' AND agent_key='general' AND step_key='generation'" in sql
    assert "operation='generate_rag' AND step_key='generation'" in sql
    assert "operation='embed_query' AND step_key='query_embedding'" in sql
    assert "operation='embed_document' AND agent_key='rules_rag'" in sql
    assert "ALTER TABLE ops.call_attempts DROP CONSTRAINT call_usage_typed" in sql
    assert "operation IN ('generate_general','generate_rag','builder_scaffold')" in sql
    assert "operation IN ('embed_document','embed_query')" in sql
    assert "ops.valid_token_counts(usage_snapshot - ARRAY['observed_model','observed_tier','provider_request_id']::text[])" in sql
    assert "usage_snapshot->>'observed_tier'='default'" in sql
    assert "ILIKE '%operation%'" not in sql


def test_failure_receipt_waits_for_shared_ledger_terminal_state():
    sql = (MIGRATIONS / "069_builder_scaffold_shared_meter.sql").read_text(encoding="utf-8")
    assert "IF q.state='generating' THEN" in sql
    assert "c.call_id IS NULL OR c.state NOT IN ('settled','usage_unknown','released_no_dispatch')" in sql
    assert "SETTLEMENT_PENDING" in sql


def test_070_lifecycle_uses_original_admission_revision_and_current_call_permit_binding():
    sql = (MIGRATIONS / "070_builder_scaffold_lifecycle_revision.sql").read_text(encoding="utf-8")
    assert "q.state='generating' AND q.revision=p_revision+1" in sql
    assert "c.permit_revision<>q.revision" in sql
    assert "q.revision<>p_revision+1 OR q.state<>'generating'" in sql
    assert "c.state<>'settled' OR c.provider_end_status<>'observed'" in sql
    assert "CREATE OR REPLACE FUNCTION security.builder_scaffold_complete(" in sql
    assert "CREATE OR REPLACE FUNCTION security.builder_scaffold_fail(" in sql
