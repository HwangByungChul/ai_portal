import hashlib
import shutil
from psycopg import sql
from scripts.migrate import MIGRATIONS,create_fixture_database,apply_migrations
from scripts.seed import seed_fixture
from test_catalog_migration import fingerprint

def test_040_dynamic_agent_favorites_preserves_prior_checksums_and_security(owned_cluster,tmp_path):
    old=tmp_path/'through039';old.mkdir()
    for p in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
        if p.name<'040_':shutil.copy2(p,old/p.name)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in old.iterdir()}
    db=create_fixture_database();state=None
    try:
        apply_migrations(db,old);state=seed_fixture(db)
        with db.admin_connection() as conn:
            before=fingerprint(conn)
            assert len(before)==51
        through=tmp_path/'through040';through.mkdir()
        for p in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
            if p.name<'041_':shutil.copy2(p,through/p.name)
        assert apply_migrations(db,through)==['040_dynamic_agent_favorites.sql']
        with db.admin_connection() as conn:
            after=fingerprint(conn)
            assert len(after)==52
            assert all(after[k]==v for k,v in before.items())
            assert dict(conn.execute("SELECT version,sha256 FROM infra.schema_migrations WHERE version<'040_' ").fetchall())==hashes
            table='dynamic_agent_favorites'
            assert conn.execute(sql.SQL('SELECT count(*) FROM portal.{}').format(sql.Identifier(table))).fetchone()[0]==0
            assert conn.execute("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid=%s::regclass",('portal.'+table,)).fetchone()[0]
            for role in ['ai_web','ai_index','ai_meter']:
                for privilege in ['SELECT','INSERT','UPDATE','DELETE']:
                    assert not conn.execute('SELECT has_table_privilege(%s,%s,%s)',(role,'portal.'+table,privilege)).fetchone()[0]
            assert conn.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='security'").fetchone()[0]==142
            assert conn.execute("SELECT has_function_privilege('ai_web','security.dynamic_favorite_mutate(uuid,uuid,uuid,uuid,uuid,jsonb)','EXECUTE')").fetchone()[0]
            for role in ['ai_index','ai_meter']:
                assert not conn.execute("SELECT has_function_privilege(%s,'security.dynamic_favorite_mutate(uuid,uuid,uuid,uuid,uuid,jsonb)','EXECUTE')",(role,)).fetchone()[0]
        assert apply_migrations(db,through)==[]
    finally:
        db.drop()
        if state:state.secret_path.unlink(missing_ok=True)
