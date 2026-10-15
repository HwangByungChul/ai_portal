import shutil
from scripts.migrate import MIGRATIONS,create_fixture_database,apply_migrations
from scripts.seed import seed_fixture
from test_catalog_migration import fingerprint
def test_035_preserves_rows_and_private_evidence_capabilities(owned_cluster,tmp_path):
    prior=tmp_path/'through034';prior.mkdir();through035=tmp_path/'through035';through035.mkdir()
    for p in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
        if p.name<'035_':shutil.copy2(p,prior/p.name)
        if p.name<'036_':shutil.copy2(p,through035/p.name)
    db=create_fixture_database();state=None
    try:
        apply_migrations(db,prior);state=seed_fixture(db)
        with db.admin_connection() as c:before=fingerprint(c);hashes=dict(c.execute('SELECT version,sha256 FROM infra.schema_migrations').fetchall())
        assert apply_migrations(db,through035)==['035_builder_evidence_shares.sql']
        with db.admin_connection() as c:
            after=fingerprint(c);assert len(after)==47 and all(after[k]==v for k,v in before.items())
            assert dict(c.execute("SELECT version,sha256 FROM infra.schema_migrations WHERE version<'035_'").fetchall())==hashes
            assert c.execute('SELECT count(*) FROM portal.builder_evidence_shares').fetchone()[0]==0
            assert c.execute("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='portal.builder_evidence_shares'::regclass").fetchone()[0]
            for role in ('ai_web','ai_index','ai_meter'):
                assert not c.execute("SELECT has_table_privilege(%s,'portal.builder_evidence_shares','SELECT,INSERT,UPDATE,DELETE')",(role,)).fetchone()[0]
            assert not c.execute("SELECT has_table_privilege('ai_policy_executor','portal.builder_evidence_shares','UPDATE,DELETE')").fetchone()[0]
            assert c.execute("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='portal.builder_evidence_shares'::regclass").fetchone()[0]
            for role in ('ai_web','ai_index','ai_meter'):
                assert not c.execute("SELECT has_table_privilege(%s,'portal.builder_evidence_shares','SELECT,INSERT,UPDATE,DELETE')",(role,)).fetchone()[0]
        assert apply_migrations(db,through035)==[]
        with db.admin_connection() as c:assert fingerprint(c)==after
    finally:
        db.drop()
        if state:state.secret_path.unlink(missing_ok=True)
