import hashlib
import shutil
import psycopg
import pytest
from scripts.migrate import MIGRATIONS, create_fixture_database, apply_migrations
from scripts.seed import seed_fixture
from test_catalog_migration import fingerprint


def test_051_preserves_rows_checksums_and_private_append_only_tables(owned_cluster,tmp_path):
    stage=tmp_path/'through050';stage.mkdir()
    for p in MIGRATIONS.glob('*.sql'):
        if p.name<'051_':shutil.copy2(p,stage/p.name)
    db=create_fixture_database();state=None
    try:
        apply_migrations(db,stage);state=seed_fixture(db)
        with db.admin_connection() as conn:before=fingerprint(conn)
        assert apply_migrations(db)==['051_meeting_context_quality.sql']
        with db.admin_connection() as conn:
            after=fingerprint(conn)
            assert all(after[k]==v for k,v in before.items())
            for table in ('meeting_run_contexts','meeting_quality_reviews'):
                assert conn.execute('SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass',('portal.'+table,)).fetchone()==(True,True)
                assert conn.execute('SELECT count(*) FROM portal.'+table).fetchone()[0]==0
            assert dict(conn.execute("SELECT version,sha256 FROM infra.schema_migrations WHERE version<'051_'").fetchall())=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.iterdir()}
        with psycopg.connect(db.runtime_dsn(),autocommit=True) as conn:
            for table in ('meeting_run_contexts','meeting_quality_reviews'):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute('SELECT * FROM portal.'+table)
        assert apply_migrations(db)==[]
    finally:
        db.drop()
        if state:state.secret_path.unlink(missing_ok=True)
