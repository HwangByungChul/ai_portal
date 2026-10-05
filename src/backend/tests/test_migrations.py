import json
from pathlib import Path
import shutil
import stat
import pytest
import psycopg
from psycopg import sql
from scripts.migrate import MIGRATIONS,MigrationError,apply_migrations,create_fixture_database,FixtureDatabase,validate_roles
from scripts.seed import HASHER,seed_fixture


def test_migration_rerun_and_checksum_reject(db_fixture,tmp_path):
    assert apply_migrations(db_fixture.db)==[]
    changed=tmp_path/'sql';shutil.copytree(MIGRATIONS,changed)
    file=changed/'001_auth_portal.sql';file.write_text(file.read_text()+'\n-- tampered\n')
    with pytest.raises(MigrationError,match='MIGRATION_CHECKSUM_CHANGED'):
        apply_migrations(db_fixture.db,changed)
    with db_fixture.db.admin_connection() as conn:
        assert conn.execute('SELECT count(*) FROM infra.schema_migrations').fetchone()[0]==11


def test_pending_failure_rolls_back_schema_and_checksum(db_fixture,tmp_path):
    changed=tmp_path/'sql';shutil.copytree(MIGRATIONS,changed)
    (changed/'003_atomic_test.sql').write_text('CREATE TABLE infra.atomic_probe(x int); SELECT 1/0;')
    with pytest.raises(psycopg.errors.DivisionByZero): apply_migrations(db_fixture.db,changed)
    with db_fixture.db.admin_connection() as conn:
        assert conn.execute("SELECT to_regclass('infra.atomic_probe')").fetchone()[0] is None
        assert conn.execute('SELECT count(*) FROM infra.schema_migrations').fetchone()[0]==11


def test_seed_rejects_existing_and_nonfixture(db_fixture):
    with pytest.raises(MigrationError,match='FIXTURE_ALREADY_SEEDED'): seed_fixture(db_fixture.db)
    wrong=FixtureDatabase('postgres',db_fixture.db.cluster)
    with pytest.raises(MigrationError,match='NOT_FIXTURE_DATABASE'): seed_fixture(wrong)
    with pytest.raises(MigrationError,match='NOT_FIXTURE_DATABASE'): apply_migrations(wrong)
    with db_fixture.db.admin_connection() as conn:
        assert conn.execute('SELECT count(*) FROM security.accounts').fetchone()[0]==13
        assert conn.execute('SELECT count(*) FROM ops.project_budget').fetchone()[0]==2


def test_wrong_fixture_marker_and_privileged_role_reject(db_fixture):
    db=db_fixture.db
    with db.admin_connection() as conn:
        conn.execute(sql.SQL("COMMENT ON DATABASE {} IS 'foreign'").format(sql.Identifier(db.name)))
    try:
        with pytest.raises(MigrationError,match='FIXTURE_MARKER_REJECTED'): apply_migrations(db)
        with pytest.raises(MigrationError,match='FIXTURE_MARKER_REJECTED'): seed_fixture(db)
        with pytest.raises(MigrationError,match='FIXTURE_MARKER_REJECTED'): db.drop()
    finally:
        from app.db import DB_MARKER
        with db.admin_connection() as conn:
            conn.execute(sql.SQL('COMMENT ON DATABASE {} IS {}').format(sql.Identifier(db.name),sql.Literal(DB_MARKER)))
    with db.admin_connection() as conn:
        with conn.transaction(force_rollback=True):
            conn.execute('ALTER ROLE ai_web BYPASSRLS')
            with pytest.raises(MigrationError,match='UNSAFE_EXISTING_ROLE'): validate_roles(conn)


def test_fixture_credentials_are_argon2_private_and_hidden(db_fixture):
    state=db_fixture.state
    assert stat.S_IMODE(state.secret_path.stat().st_mode)==0o600
    assert stat.S_IMODE(state.secret_path.parent.stat().st_mode)==0o700
    with db_fixture.db.admin_connection() as conn:
        values=conn.execute('SELECT login_id,password_hash FROM security.accounts').fetchall()
    assert len(values)==13
    for login,hashed in values:
        password=state.passwords[login.upper()]
        assert len(password)>=15
        assert hashed.startswith('$argon2id$v=19$m=19456,t=2,p=1$')
        assert HASHER.verify(hashed,password)
        assert password not in repr(db_fixture) and password not in repr(state)
    async def check():
        ctx=await db_fixture.context('A-U1','A')
        assert ctx.csrf_secret not in repr(ctx)
    db_fixture.run(check())


def test_first_migration_batch_failure_has_no_partial_schema(owned_cluster,tmp_path):
    db=create_fixture_database()
    try:
        changed=tmp_path/'sql';shutil.copytree(MIGRATIONS,changed)
        (changed/'003_fail.sql').write_text('SELECT 1/0;')
        with pytest.raises(psycopg.errors.DivisionByZero): apply_migrations(db,changed)
        with db.admin_connection() as conn:
            assert conn.execute("SELECT to_regclass('infra.schema_migrations'),to_regclass('security.accounts')").fetchone()==(None,None)
            assert conn.execute('SELECT datconnlimit FROM pg_database WHERE datname=%s',(db.name,)).fetchone()[0]==0
    finally: db.drop()
