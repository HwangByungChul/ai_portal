import hashlib,shutil
from scripts.migrate import MIGRATIONS,create_fixture_database,apply_migrations
from scripts.seed import seed_fixture
from test_catalog_migration import fingerprint
def test_032_preserves_prior_rows_checksums_and_private_trial_privileges(owned_cluster,tmp_path):
    prior=tmp_path/'through031';prior.mkdir();through032=tmp_path/'through032';through032.mkdir()
    for p in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
        if p.name<'032_':shutil.copy2(p,prior/p.name)
        if p.name<'033_':shutil.copy2(p,through032/p.name)
    db=create_fixture_database();state=None
    try:
        apply_migrations(db,prior);state=seed_fixture(db)
        with db.admin_connection() as c:before=fingerprint(c);hashes=dict(c.execute('SELECT version,sha256 FROM infra.schema_migrations').fetchall())
        assert apply_migrations(db,through032)==['032_builder_trials.sql']
        with db.admin_connection() as c:
            after=fingerprint(c);assert all(after[k]==v for k,v in before.items())
            assert dict(c.execute("SELECT version,sha256 FROM infra.schema_migrations WHERE version<'032_'").fetchall())==hashes
            assert len(after)==43 and c.execute('SELECT count(*) FROM portal.builder_trials').fetchone()[0]==0
            assert c.execute("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='portal.builder_trials'::regclass").fetchone()[0]
            for role in ('ai_web','ai_index','ai_meter'):
                assert not c.execute("SELECT has_table_privilege(%s,'portal.builder_trials','SELECT,INSERT,UPDATE,DELETE')",(role,)).fetchone()[0]
            for name in ('builder_trial_compose(jsonb,jsonb)','builder_trial_guard(uuid,uuid,uuid)'):
                assert not c.execute('SELECT has_function_privilege(%s,%s,%s)',('ai_web','security.'+name,'EXECUTE')).fetchone()[0]
        assert apply_migrations(db,through032)==[]
        with db.admin_connection() as c:assert fingerprint(c)==after
    finally:
        db.drop()
        if state:state.secret_path.unlink(missing_ok=True)
