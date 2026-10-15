import hashlib,shutil
from uuid import uuid4
import psycopg
import pytest
from scripts.migrate import MIGRATIONS,create_fixture_database,apply_migrations
from scripts.seed import seed_fixture
from test_catalog_migration import fingerprint


def test_049_preserves_existing_rows_checksums_and_null_metadata(owned_cluster,tmp_path):
    old=tmp_path/'through048';old.mkdir()
    for path in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
        if path.name<'049_':shutil.copy2(path,old/path.name)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in old.iterdir()}
    db=create_fixture_database();state=None
    try:
        apply_migrations(db,old);state=seed_fixture(db)
        with db.admin_connection() as conn:
            workflow=uuid4();version=uuid4()
            conn.execute('INSERT INTO portal.workflows(tenant_id,workflow_id,owner_id,client_request_id) VALUES(%s,%s,%s,%s)',(state.tenant_ids['A'],workflow,state.actor_ids['A-ADM'],uuid4()))
            conn.execute("INSERT INTO portal.workflow_versions(tenant_id,workflow_id,version_id,revision,created_by,client_request_id,definition,version_digest,audience,member_ids,expected_head_revision) VALUES(%s,%s,%s,1,%s,%s,'{}',%s,'all','{}',0)",(state.tenant_ids['A'],workflow,version,state.actor_ids['A-ADM'],uuid4(),'a'*64))
            before=fingerprint(conn);assert len(before)==64
        stage=tmp_path/'only049';stage.mkdir()
        for migration in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
            if migration.name<'050_':shutil.copy2(migration,stage/migration.name)
        assert apply_migrations(db,stage)==['049_meeting_workflow_binding.sql']
        with db.admin_connection() as conn:
            after=fingerprint(conn);assert len(after)==65
            after[('portal','workflow_versions')]=conn.execute("SELECT count(*),md5(COALESCE(string_agg((to_jsonb(t)-ARRAY['use_case_id','use_case_digest','use_case_revision'])::text,'' ORDER BY (to_jsonb(t)-ARRAY['use_case_id','use_case_digest','use_case_revision'])::text),'')) FROM portal.workflow_versions t").fetchone()
            assert all(after[name]==value for name,value in before.items())
            assert conn.execute('SELECT use_case_id,use_case_digest,use_case_revision FROM portal.workflow_versions WHERE version_id=%s',(version,)).fetchone()==(None,None,None)
            with pytest.raises(psycopg.errors.CheckViolation):
                with conn.transaction():conn.execute("UPDATE portal.workflow_versions SET use_case_id='AGENT_03',use_case_revision=0 WHERE version_id=%s",(version,))
            assert dict(conn.execute("SELECT version,sha256 FROM infra.schema_migrations WHERE version<'049_'").fetchall())==hashes
        with psycopg.connect(db.runtime_dsn(),autocommit=True) as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute('SELECT * FROM portal.use_case_heads')
        assert apply_migrations(db,stage)==[]
    finally:
        db.drop()
        if state:state.secret_path.unlink(missing_ok=True)
