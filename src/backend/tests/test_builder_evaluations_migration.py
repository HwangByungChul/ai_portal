import shutil
from scripts.migrate import MIGRATIONS,create_fixture_database,apply_migrations
from scripts.seed import seed_fixture
from test_catalog_migration import fingerprint
def test_034_preserves_prior_rows_and_evaluation_capabilities(owned_cluster,tmp_path):
    prior=tmp_path/'through033';prior.mkdir();through034=tmp_path/'through034';through034.mkdir()
    for p in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
        if p.name<'034_':shutil.copy2(p,prior/p.name)
        if p.name<'035_':shutil.copy2(p,through034/p.name)
    db=create_fixture_database();state=None
    try:
        apply_migrations(db,prior);state=seed_fixture(db)
        with db.admin_connection() as c:before=fingerprint(c);hashes=dict(c.execute('SELECT version,sha256 FROM infra.schema_migrations').fetchall())
        assert apply_migrations(db,through034)==['034_builder_evaluations.sql']
        with db.admin_connection() as c:
            after=fingerprint(c);assert len(after)==46 and all(after[k]==v for k,v in before.items())
            assert dict(c.execute("SELECT version,sha256 FROM infra.schema_migrations WHERE version<'034_'").fetchall())==hashes
            assert c.execute('SELECT count(*) FROM portal.builder_evaluations').fetchone()[0]==0
            assert c.execute("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='portal.builder_evaluations'::regclass").fetchone()[0]
            for role in ('ai_web','ai_index','ai_meter'):
                assert not c.execute("SELECT has_table_privilege(%s,'portal.builder_evaluations','SELECT,INSERT,UPDATE,DELETE')",(role,)).fetchone()[0]
            assert not c.execute("SELECT has_table_privilege('ai_policy_executor','portal.builder_evaluations','UPDATE,DELETE')").fetchone()[0]
            assert c.execute("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='portal.builder_cases'::regclass").fetchone()[0]
            for role in ('ai_web','ai_index','ai_meter'):
                assert not c.execute("SELECT has_table_privilege(%s,'portal.builder_cases','SELECT,INSERT,UPDATE,DELETE')",(role,)).fetchone()[0]
        assert apply_migrations(db,through034)==[]
        with db.admin_connection() as c:assert fingerprint(c)==after
    finally:
        db.drop()
        if state:state.secret_path.unlink(missing_ok=True)
