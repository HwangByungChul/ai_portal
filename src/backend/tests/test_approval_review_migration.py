import hashlib,shutil
from uuid import uuid4
import psycopg,pytest
from scripts.migrate import MIGRATIONS,create_fixture_database,apply_migrations
from scripts.seed import seed_fixture
from test_catalog_migration import fingerprint

def test_050_preserves_rows_checksums_and_null_manifest(owned_cluster,tmp_path):
    old=tmp_path/'through049';old.mkdir()
    for p in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
        if p.name<'050_':shutil.copy2(p,old/p.name)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in old.iterdir()};db=create_fixture_database();state=None
    try:
        apply_migrations(db,old);state=seed_fixture(db)
        with db.admin_connection() as conn:
            workflow=uuid4();version=uuid4()
            conn.execute('INSERT INTO portal.workflows(tenant_id,workflow_id,owner_id,client_request_id) VALUES(%s,%s,%s,%s)',(state.tenant_ids['A'],workflow,state.actor_ids['A-ADM'],uuid4()))
            conn.execute("INSERT INTO portal.workflow_versions(tenant_id,workflow_id,version_id,revision,created_by,client_request_id,definition,version_digest,audience,member_ids,expected_head_revision,status) VALUES(%s,%s,%s,1,%s,%s,'{}',%s,'all','{}',0,'approved')",(state.tenant_ids['A'],workflow,version,state.actor_ids['A-ADM'],uuid4(),'a'*64))
            before=fingerprint(conn)
        assert apply_migrations(db)==['050_tool_workflow_approval_reviews.sql']
        with db.admin_connection() as conn:
            after=fingerprint(conn)
            after[('portal','workflow_versions')]=conn.execute("SELECT count(*),md5(COALESCE(string_agg((to_jsonb(t)-'manifest_snapshot')::text,'' ORDER BY (to_jsonb(t)-'manifest_snapshot')::text),'')) FROM portal.workflow_versions t").fetchone()
            assert all(after[n]==v for n,v in before.items()) and len(after)==66
            assert conn.execute('SELECT manifest_snapshot FROM portal.workflow_versions WHERE version_id=%s',(version,)).fetchone()==(None,)
            assert dict(conn.execute("SELECT version,sha256 FROM infra.schema_migrations WHERE version<'050_'").fetchall())==hashes
            assert conn.execute('SELECT count(*) FROM portal.approval_reviews').fetchone()[0]==0
        with psycopg.connect(db.runtime_dsn(),autocommit=True) as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute('SELECT * FROM portal.approval_reviews')
            with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute("SELECT security.tool_approval_control_v046(NULL,NULL,'list',NULL,'{}',NULL)")
        assert apply_migrations(db)==[]
    finally:
        db.drop()
        if state:state.secret_path.unlink(missing_ok=True)
