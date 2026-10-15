import hashlib,shutil
from psycopg import sql
from scripts.migrate import MIGRATIONS,create_fixture_database,apply_migrations
from scripts.seed import seed_fixture
from test_catalog_migration import fingerprint


def test_030_preserves_every_prior_row_and_seals_capabilities(owned_cluster,tmp_path):
    old=tmp_path/'through029';old.mkdir()
    for p in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
        if p.name<'030_':shutil.copy2(p,old/p.name)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in old.iterdir()}
    db=create_fixture_database();state=None
    try:
        apply_migrations(db,old);state=seed_fixture(db)
        with db.admin_connection() as conn:before=fingerprint(conn)
        through=tmp_path/'through030';through.mkdir()
        for p in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
            if p.name<'031_':shutil.copy2(p,through/p.name)
        assert apply_migrations(db,through)==['030_builder_profiles.sql']
        with db.admin_connection() as conn:
            after=fingerprint(conn);assert all(after[k]==v for k,v in before.items())
            assert dict(conn.execute("SELECT version,sha256 FROM infra.schema_migrations WHERE version<'030_'").fetchall())==hashes
            for table in ('portal.builder_profiles','portal.builder_receipts'):
                assert conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(*table.split('.')))).fetchone()[0]==0
                assert conn.execute('SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid=%s::regclass',(table,)).fetchone()[0]
                for role in ('ai_web','ai_index','ai_meter'):
                    assert not conn.execute('SELECT has_table_privilege(%s,%s,\'SELECT,INSERT,UPDATE,DELETE\')',(role,table)).fetchone()[0]
                assert not conn.execute('SELECT has_table_privilege(\'ai_policy_executor\',%s,\'UPDATE,DELETE\')',(table,)).fetchone()[0]
            assert not conn.execute("SELECT has_function_privilege('ai_web','security.asset_registry_v029(uuid,uuid,text,uuid,jsonb,uuid)','EXECUTE')").fetchone()[0]
            assert not conn.execute("SELECT has_function_privilege('ai_web','security.builder_profile_validate(jsonb,jsonb)','EXECUTE')").fetchone()[0]
        assert apply_migrations(db,through)==[]
        with db.admin_connection() as conn:before031=fingerprint(conn)
        through031=tmp_path/'through031';through031.mkdir()
        for p in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
            if p.name<'032_':shutil.copy2(p,through031/p.name)
        assert apply_migrations(db,through031)==['031_builder_scope_dedup.sql']
        with db.admin_connection() as conn:assert fingerprint(conn)==before031
        assert apply_migrations(db,through031)==[]
    finally:
        db.drop()
        if state:state.secret_path.unlink(missing_ok=True)
