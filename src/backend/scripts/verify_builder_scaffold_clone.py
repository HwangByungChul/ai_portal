"""Run the migration chain only against an explicitly named disposable clone.

The operator must create a disposable fixture clone and set
AI_BUILDER_DISPOSABLE_CLONE_DSN. This script refuses unnamed/shared databases and
always rolls back its migration transaction. It is intentionally never called by
normal tests against DATABASE_URL.
"""
from __future__ import annotations
import os
from pathlib import Path
from urllib.parse import urlparse
import psycopg


def run_builder_clone_verification(dsn: str | None = None) -> dict[str, object]:
    target = dsn or os.getenv("AI_BUILDER_DISPOSABLE_CLONE_DSN")
    if not target:
        raise RuntimeError("AI_BUILDER_DISPOSABLE_CLONE_DSN_REQUIRED")
    database = urlparse(target).path.rsplit("/", 1)[-1]
    if not database.endswith("_builder_clone"):
        raise RuntimeError("DISPOSABLE_BUILDER_CLONE_NAME_REQUIRED")
    migration_dir = Path(__file__).resolve().parent.parent / "migrations"
    files = sorted(migration_dir.glob("*.sql"))
    with psycopg.connect(target, autocommit=False) as conn:
        try:
            with conn.cursor() as cur:
                for path in files:
                    cur.execute(path.read_text(encoding="utf-8"))
                cur.execute("""
                    SELECT
                      (SELECT relrowsecurity AND relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='portal' AND c.relname='builder_scaffold_proposals'),
                      has_table_privilege('ai_web','portal.builder_scaffold_proposals','SELECT'),
                      to_regprocedure('security.call_meter(uuid,uuid,bigint,bytea,jsonb,text,boolean)') IS NOT NULL,
                      to_regprocedure('security.builder_scaffold_dispatch(uuid,uuid,uuid,uuid,date,text,bytea,bytea)') IS NOT NULL
                """)
                rls_forced, web_select, shared_meter, dispatch_capability = cur.fetchone()
                assert rls_forced is True
                assert web_select is False
                assert shared_meter is True and dispatch_capability is True
            conn.rollback()
        except Exception:
            conn.rollback()
            raise
    return {"migrations": len(files), "forced_rls": True, "no_web_payload_select": True,
            "shared_meter": True, "rollback_verified": True}
