"""Checksum migrations restricted to the project-owned fixture cluster."""
import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import secrets
import shlex
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from app.db import DB_MARKER, FIXTURE_PREFIX
from scripts.devdb import DEFAULT_RUNTIME, DevCluster, _read_private, _write_private

MIGRATIONS = Path(__file__).resolve().parents[1] / 'migrations'
ROLES = ('ai_owner', 'ai_policy_executor', 'ai_web', 'ai_index', 'ai_meter')
LOGIN_ROLES = ('ai_web', 'ai_index', 'ai_meter')

class MigrationError(RuntimeError):
    pass

@dataclass(frozen=True)
class FixtureDatabase:
    name: str
    cluster: DevCluster = field(repr=False)

    def admin_connection(self):
        if not re.fullmatch(FIXTURE_PREFIX + r'[0-9a-f]{32}', self.name):
            raise MigrationError('NOT_FIXTURE_DATABASE')
        if self.cluster.port != 55432 or self.cluster.runtime != DEFAULT_RUNTIME.resolve():
            raise MigrationError('WRONG_FIXTURE_CLUSTER')
        self.cluster.status()
        return psycopg.connect(host='127.0.0.1', port=55432, dbname=self.name,
            user='mvp_bootstrap', passfile=str(self.cluster.passfile_path), sslmode='disable',
            connect_timeout=3, autocommit=True, options='-c timezone=UTC -c statement_timeout=5000')

    def verify(self, conn):
        if not re.fullmatch(FIXTURE_PREFIX + r'[0-9a-f]{32}', self.name):
            raise MigrationError('NOT_FIXTURE_DATABASE')
        row = conn.execute("SELECT current_database(),session_user,shobj_description(oid,'pg_database') "
            "FROM pg_database WHERE datname=current_database()").fetchone()
        if row != (self.name, 'mvp_bootstrap', DB_MARKER):
            raise MigrationError('FIXTURE_MARKER_REJECTED')

    def drop(self):
        with self.admin_connection() as conn:
            self.verify(conn)
        with self.cluster.connect() as conn:
            conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(self.name)))

    def runtime_dsn(self, role='ai_web'):
        if role not in LOGIN_ROLES:
            raise MigrationError('ROLE_REJECTED')
        credentials = _role_credentials(self.cluster)
        return make_conninfo(host='127.0.0.1', port=55432, dbname=self.name, user=role,
            password=credentials[role], sslmode='disable', connect_timeout=3)


def _role_credentials(cluster):
    path = cluster.runtime / 'runtime-roles.json'
    if not path.exists():
        _write_private(path, json.dumps({role: secrets.token_urlsafe(32) for role in LOGIN_ROLES}))
    values = json.loads(_read_private(path))
    if set(values) != set(LOGIN_ROLES) or not all(isinstance(v,str) and len(v)>=40 for v in values.values()):
        raise MigrationError('ROLE_CREDENTIALS_REJECTED')
    return values


def create_fixture_database():
    cluster = DevCluster()
    if cluster.status()['state'] != 'running':
        raise MigrationError('CLUSTER_NOT_RUNNING')
    name = FIXTURE_PREFIX + uuid4().hex
    with cluster.connect() as conn:
        conn.execute(sql.SQL('CREATE DATABASE {} CONNECTION LIMIT 0').format(sql.Identifier(name)))
        conn.execute(sql.SQL('COMMENT ON DATABASE {} IS {}').format(sql.Identifier(name),sql.Literal(DB_MARKER)))
        conn.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(name)))
    return FixtureDatabase(name, cluster)


def validate_roles(conn):
    for role in ROLES:
        row = conn.execute('SELECT rolcanlogin,rolsuper,rolbypassrls,rolinherit,rolcreatedb,rolcreaterole,rolreplication '
            'FROM pg_roles WHERE rolname=%s', (role,)).fetchone()
        if row and (row[0] != (role in LOGIN_ROLES) or any(row[1:])):
            raise MigrationError('UNSAFE_EXISTING_ROLE')
    if conn.execute('SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid '
        'JOIN pg_roles u ON u.oid=m.member WHERE r.rolname=ANY(%s) OR u.rolname=ANY(%s) LIMIT 1',
        (list(ROLES),list(ROLES))).fetchone():
        raise MigrationError('UNSAFE_ROLE_MEMBERSHIP')


def apply_migrations(db, migration_dir=MIGRATIONS):
    with db.admin_connection() as conn:
        db.verify(conn)
        validate_roles(conn)
        credentials = _role_credentials(db.cluster)
        with conn.transaction():
            conn.execute('SELECT pg_advisory_xact_lock(250002)')
            conn.execute('CREATE SCHEMA IF NOT EXISTS infra')
            conn.execute('CREATE TABLE IF NOT EXISTS infra.schema_migrations('
                'version text PRIMARY KEY,sha256 text NOT NULL,applied_at timestamptz NOT NULL DEFAULT clock_timestamp())')
            applied = dict(conn.execute('SELECT version,sha256 FROM infra.schema_migrations').fetchall())
            paths = sorted(migration_dir.glob('[0-9][0-9][0-9]_*.sql'))
            if set(applied)-{p.name for p in paths}:
                raise MigrationError('MIGRATION_FILE_MISSING')
            completed=[]
            for path in paths:
                text=path.read_text(); checksum=hashlib.sha256(path.read_bytes()).hexdigest()
                if path.name in applied:
                    if applied[path.name] != checksum:
                        raise MigrationError('MIGRATION_CHECKSUM_CHANGED')
                    continue
                conn.execute(text)
                conn.execute('INSERT INTO infra.schema_migrations(version,sha256) VALUES(%s,%s)',(path.name,checksum))
                completed.append(path.name)
            validate_roles(conn)
            for role in LOGIN_ROLES:
                conn.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(sql.Identifier(role),sql.Literal(credentials[role])))
            conn.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO ai_web,ai_index,ai_meter').format(sql.Identifier(db.name)))
            conn.execute(sql.SQL('ALTER DATABASE {} CONNECTION LIMIT -1').format(sql.Identifier(db.name)))
    return completed


def write_app_environment(db):
    path=db.cluster.runtime / 'app.env'
    value=f'AI_WEB_DSN={shlex.quote(db.runtime_dsn())}\nAI_LOGIN_HMAC_SECRET={shlex.quote(secrets.token_urlsafe(32))}\n'
    _write_private(path,value)
    return path


def main():
    parser=argparse.ArgumentParser(description='Initialize one new disposable project fixture DB')
    parser.add_argument('--fixture', required=True, choices=['A-auth'])
    args=parser.parse_args()
    try:
        cluster=DevCluster()
        cluster._validate()
        if any((cluster.runtime/name).exists() for name in ('active-fixture.json','app.env')):
            raise MigrationError('FIXTURE_RUNTIME_ALREADY_CONFIGURED')
        db=create_fixture_database()
        completed=apply_migrations(db)
        _write_private(db.cluster.runtime/'active-fixture.json',json.dumps({'database':db.name,'marker':DB_MARKER}))
        write_app_environment(db)
        print(json.dumps({'database':db.name,'applied':completed,'fixture':args.fixture}))
        return 0
    except Exception:
        print(json.dumps({'error':{'code':'FIXTURE_INITIALIZATION_FAILED'}}))
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
