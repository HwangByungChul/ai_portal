"""Web-only database pool and transaction-scoped, server-derived identity."""
from contextlib import asynccontextmanager
import hashlib
from pathlib import Path
import re

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.types import AuthContext

FIXTURE_PREFIX = 'ai_portal_mvp_test_'
RUNTIME_KEY = hashlib.sha256(str((Path(__file__).resolve().parents[1] / '.runtime').resolve()).encode()).hexdigest()[:12]
DB_MARKER = f'ai-platform:fixture:A-auth:{RUNTIME_KEY}'


class DatabaseBoundaryError(RuntimeError):
    pass


def make_web_pool(dsn: str, size: int = 4) -> AsyncConnectionPool:
    # Never inherit host/user/database from another project's PG environment.
    try:
        options = conninfo_to_dict(dsn)
    except psycopg.Error:
        raise DatabaseBoundaryError('WEB_CONFIGURATION_REJECTED') from None
    if (options.get('host') != '127.0.0.1' or options.get('port') != '55432'
            or options.get('user') != 'ai_web' or options.get('hostaddr') not in (None, '127.0.0.1')
            or not re.fullmatch(FIXTURE_PREFIX + r'[0-9a-f]{32}', options.get('dbname', ''))):
        raise DatabaseBoundaryError('WEB_CONFIGURATION_REJECTED')
    return AsyncConnectionPool(dsn, min_size=1, max_size=size, timeout=5, open=False,
        kwargs={'autocommit': True, 'row_factory': dict_row,
                'options': '-c timezone=UTC -c statement_timeout=5000 -c lock_timeout=2000'},
        configure=verify_web_connection, check=verify_web_connection)


async def verify_web_connection(conn):
    try:
        await _verify_web_connection(conn)
    except BaseException:
        # Pool configure callbacks do not close rejected connections in this pinned version.
        await conn.close()
        raise


async def _verify_web_connection(conn):
    row = await (await conn.execute(
        "SELECT session_user,current_user,current_database() AS database, "
        "current_setting('port') AS port,rolsuper,rolbypassrls,rolinherit,rolcreatedb,rolcreaterole,rolreplication, "
        "shobj_description(d.oid,'pg_database') AS marker,d.datdba=r.oid AS owns_database, "
        "EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid) AS inherited, "
        "EXISTS(SELECT 1 FROM pg_namespace n WHERE n.nspowner=r.oid AND n.nspname IN ('security','portal','ops')) "
        "OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE c.relowner=r.oid AND n.nspname IN ('security','portal','ops')) AS owns_content "
        "FROM pg_roles r JOIN pg_database d ON d.datname=current_database() WHERE r.rolname=session_user"
    )).fetchone()
    if (not row or row['session_user'] != 'ai_web' or row['current_user'] != 'ai_web'
            or row['marker'] != DB_MARKER or row['port'] != '55432'
            or any(row[k] for k in ('rolsuper','rolbypassrls','rolinherit','rolcreatedb','rolcreaterole','rolreplication','inherited','owns_content','owns_database'))):
        raise DatabaseBoundaryError('WEB_DATABASE_REJECTED')


@asynccontextmanager
async def open_web_pool(dsn: str, size: int = 4):
    pool = make_web_pool(dsn, size)
    try:
        try:
            await pool.open()
            await pool.wait(timeout=5)
        except (psycopg.Error, DatabaseBoundaryError):
            raise DatabaseBoundaryError('WEB_DATABASE_UNAVAILABLE') from None
        yield pool
    finally:
        await pool.close()


@asynccontextmanager
async def tenant_transaction(pool: AsyncConnectionPool, ctx: AuthContext):
    if ctx.tenant_id is None:
        raise ValueError('TENANT_CONTEXT_REQUIRED')
    async with pool.connection() as conn:
        async with conn.transaction():
            # The role and identity must still match authoritative session/membership state.
            row = await (await conn.execute('SELECT * FROM security.current_membership(%s,%s)',
                (ctx.session_id, ctx.tenant_id))).fetchone()
            if not row:
                raise ValueError('CONTEXT_UNAVAILABLE')
            for key,value in (('app.user_id', ctx.user_id), ('app.tenant_id', ctx.tenant_id), ('app.session_id', ctx.session_id)):
                await conn.execute('SELECT set_config(%s,%s,true)', (key,str(value)))
            # Also binds the supplied user to that session: mismatched internal contexts fail closed.
            row = await (await conn.execute('SELECT security.can_read_agent(%s) AS allowed', (ctx.tenant_id,))).fetchone()
            if not row['allowed']:
                raise ValueError('CONTEXT_UNAVAILABLE')
            yield conn
