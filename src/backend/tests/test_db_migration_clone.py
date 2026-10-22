"""Static and boundary validation for new migrations 065, 066, and 067."""
from pathlib import Path
import re
import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def test_migrations_numbering_continuity():
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    numbers = []
    for f in sql_files:
        match = re.match(r"^(\d{3})_", f.name)
        if match:
            numbers.append(int(match.group(1)))

    assert numbers, "No migrations found"
    # Ensure sequential numbering from 0 to 67 without duplicates or missing gaps
    expected = list(range(len(numbers)))
    assert numbers == expected, f"Migration sequence gap or duplicate detected: {numbers}"


def test_065_publication_ledger_syntax_and_security():
    path = MIGRATIONS_DIR / "065_mcp_tool_publication_ledger.sql"
    assert path.exists()
    content = path.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS portal.mcp_tool_publications" in content
    assert "ENABLE ROW LEVEL SECURITY" in content
    assert "mcp_tool_publications_tenant_isolation" in content
    assert "GRANT SELECT ON portal.mcp_tool_publications TO ai_web" in content
    assert "CHECK (status IN ('active', 'retired', 'superseded'))" in content


def test_066_publication_rpc_syntax_and_self_approval_block():
    path = MIGRATIONS_DIR / "066_mcp_tool_publication_rpc.sql"
    assert path.exists()
    content = path.read_text(encoding="utf-8")

    assert "CREATE OR REPLACE FUNCTION security.mcp_tool_publication_control" in content
    assert "SECURITY DEFINER" in content
    assert "OWNER TO ai_policy_executor" in content
    assert "appr.requester_id = u" in content
    assert "APPROVAL_DENIED" in content
    assert "GRANT EXECUTE ON FUNCTION security.mcp_tool_publication_control" in content


def test_067_audit_ledger_syntax_and_immutable_trigger():
    path = MIGRATIONS_DIR / "067_mcp_tool_audit_ledger.sql"
    assert path.exists()
    content = path.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS portal.mcp_tool_audit_events" in content
    assert "ENABLE ROW LEVEL SECURITY" in content
    assert "BEFORE UPDATE OR DELETE ON portal.mcp_tool_audit_events" in content
    assert "AUDIT_LOG_IMMUTABLE" in content
    assert "GRANT SELECT, INSERT ON portal.mcp_tool_audit_events TO ai_web" in content


def test_runtime_clone_harness_structure():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import verify_migration_clone_runtime as harness

    migration_files = harness.get_migration_files()
    assert len(migration_files) >= 68
    assert migration_files[-1].name == "067_mcp_tool_audit_ledger.sql"

    # Run check against target database if available, or confirm graceful fallback
    res = harness.run_runtime_clone_verification("postgresql://invalid-host-probing:5432/nonexistent")
    assert res["connected"] is False
    assert "rollback_verified" in res
