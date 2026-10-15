import hashlib
import shutil
from psycopg import sql
from scripts.migrate import MIGRATIONS,create_fixture_database,apply_migrations
from scripts.seed import seed_fixture


def fingerprint(conn):
    tables=conn.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname IN ('security','portal','rag','ops') ORDER BY 1,2").fetchall()
    return {(schema,table):conn.execute(sql.SQL("SELECT count(*),md5(COALESCE(string_agg(to_jsonb(t)::text,'' ORDER BY to_jsonb(t)::text),'')) FROM {}.{} t").format(sql.Identifier(schema),sql.Identifier(table))).fetchone() for schema,table in tables}


def test_029_preserves_all_rows_prior_sql_and_forced_rls(owned_cluster,tmp_path):
    old=tmp_path/'old';old.mkdir()
    for p in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
        if p.name<'029_':shutil.copy2(p,old/p.name)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in old.iterdir()}
    db=create_fixture_database();state=None
    try:
        apply_migrations(db,old);state=seed_fixture(db)
        with db.admin_connection() as conn:before=fingerprint(conn)
        through=tmp_path/'through029';through.mkdir()
        for p in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
            if p.name<'030_':shutil.copy2(p,through/p.name)
        assert apply_migrations(db,through)==['029_agent_catalog_access.sql']
        with db.admin_connection() as conn:
            after=fingerprint(conn);assert all(after[k]==v for k,v in before.items())
            assert dict(conn.execute("SELECT version,sha256 FROM infra.schema_migrations WHERE version<'029_' ").fetchall())==hashes
            for table in ['agent_access','agent_favorites','catalog_mutations']:
                assert conn.execute(sql.SQL('SELECT count(*) FROM portal.{}').format(sql.Identifier(table))).fetchone()[0]==0
                assert conn.execute("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid=%s::regclass",('portal.'+table,)).fetchone()[0]
                for role in ['ai_web','ai_index','ai_meter']:
                    for privilege in ['SELECT','INSERT','UPDATE','DELETE']:
                        assert not conn.execute('SELECT has_table_privilege(%s,%s,%s)',(role,'portal.'+table,privilege)).fetchone()[0]
            assert not conn.execute("SELECT has_table_privilege('ai_policy_executor','portal.catalog_mutations','UPDATE')").fetchone()[0]
            assert not conn.execute("SELECT has_function_privilege('ai_web','security.agent_access_guard(uuid,text)','EXECUTE')").fetchone()[0]
        assert apply_migrations(db,through)==[]
    finally:
        db.drop()
        if state:state.secret_path.unlink(missing_ok=True)
