import hashlib
import shutil
from psycopg import sql
from scripts.migrate import MIGRATIONS,create_fixture_database,apply_migrations
from scripts.seed import seed_fixture


def fingerprint(conn):
    tables=conn.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname IN ('security','portal','rag','ops') ORDER BY 1,2").fetchall()
    return {(schema,table):conn.execute(sql.SQL("SELECT count(*),md5(COALESCE(string_agg(to_jsonb(t)::text,'' ORDER BY to_jsonb(t)::text),'')) FROM {}.{} t").format(sql.Identifier(schema),sql.Identifier(table))).fetchone() for schema,table in tables}


def test_additive_migration_preserves_every_existing_row_and_rerun(owned_cluster,tmp_path):
    old=tmp_path/'old-sql';old.mkdir()
    for path in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
        if path.name<'027_asset_registry.sql':shutil.copy2(path,old/path.name)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in old.iterdir()}
    db=create_fixture_database();state=None
    try:
        apply_migrations(db,old);state=seed_fixture(db)
        with db.admin_connection() as conn:before=fingerprint(conn)
        through027=tmp_path/'through027';through027.mkdir()
        for path in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
            if path.name<'028_':shutil.copy2(path,through027/path.name)
        assert apply_migrations(db,through027)==['027_asset_registry.sql']
        with db.admin_connection() as conn:
            after=fingerprint(conn);assert all(after[key]==value for key,value in before.items())
            assert dict(conn.execute('SELECT version,sha256 FROM infra.schema_migrations WHERE version<>%s',('027_asset_registry.sql',)).fetchall())==hashes
            assert conn.execute('SELECT count(*) FROM portal.asset_registry_records').fetchone()[0]==0
            assert conn.execute('SELECT count(*) FROM portal.agent_configs').fetchone()[0]==4
            # Version content cannot be updated even by the RPC owner.
            assert not conn.execute("SELECT has_column_privilege('ai_policy_executor','portal.asset_versions','config','UPDATE')").fetchone()[0]
        assert apply_migrations(db,through027)==[]
    finally:
        db.drop()
        if state:state.secret_path.unlink(missing_ok=True)
