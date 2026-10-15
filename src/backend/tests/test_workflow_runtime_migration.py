import hashlib
import shutil
from uuid import uuid4
import psycopg
import pytest
from scripts.migrate import MIGRATIONS,create_fixture_database,apply_migrations
from scripts.seed import seed_fixture
from test_catalog_migration import fingerprint


def test_048_preserves_prior_rows_checksums_and_unsealed_legacy_versions(owned_cluster,tmp_path):
    old=tmp_path/'through047';old.mkdir()
    for path in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
        if path.name<'048_':shutil.copy2(path,old/path.name)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in old.iterdir()}
    db=create_fixture_database();state=None
    try:
        apply_migrations(db,old);state=seed_fixture(db);workflow=uuid4();version=uuid4()
        with db.admin_connection() as conn:
            conn.execute('INSERT INTO portal.workflows(tenant_id,workflow_id,owner_id,client_request_id) VALUES(%s,%s,%s,%s)',(state.tenant_ids['A'],workflow,state.actor_ids['A-ADM'],uuid4()))
            conn.execute("INSERT INTO portal.workflow_versions(tenant_id,workflow_id,version_id,revision,created_by,client_request_id,definition,version_digest,audience,member_ids,expected_head_revision) VALUES(%s,%s,%s,1,%s,%s,'{}',%s,'all','{}',0)",(state.tenant_ids['A'],workflow,version,state.actor_ids['A-ADM'],uuid4(),'a'*64))
            before=fingerprint(conn);assert len(before)==62
        through048=tmp_path/'through048';through048.mkdir()
        for path in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
            if path.name<'049_':shutil.copy2(path,through048/path.name)
        assert apply_migrations(db,through048)==['048_workflow_execution_ledger.sql']
        with db.admin_connection() as conn:
            after=fingerprint(conn);assert len(after)==64
            after[('portal','workflow_versions')]=conn.execute("SELECT count(*),md5(COALESCE(string_agg((to_jsonb(t)-ARRAY['execution_mode','runtime_digest'])::text,'' ORDER BY (to_jsonb(t)-ARRAY['execution_mode','runtime_digest'])::text),'')) FROM portal.workflow_versions t").fetchone()
            assert all(after[name]==row for name,row in before.items())
            assert dict(conn.execute("SELECT version,sha256 FROM infra.schema_migrations WHERE version<'048_'").fetchall())==hashes
            assert conn.execute('SELECT execution_mode,runtime_digest FROM portal.workflow_versions WHERE version_id=%s',(version,)).fetchone()==(None,None)
            with pytest.raises(psycopg.errors.CheckViolation):
                with conn.transaction():conn.execute("UPDATE portal.workflow_versions SET definition='{}'::jsonb||'{\"tamper\":true}'::jsonb WHERE version_id=%s",(version,))
        assert apply_migrations(db,through048)==[]
    finally:
        db.drop()
        if state:state.secret_path.unlink(missing_ok=True)
