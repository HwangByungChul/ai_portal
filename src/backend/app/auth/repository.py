"""Fixed, parameter-bound control SQL. Credentials never leave the auth service."""
from app.types import SessionView


class AuthRepository:
    async def credential(self, conn, login):
        return await (await conn.execute('SELECT * FROM security.load_login_credential(%s)', (login,))).fetchone()

    async def window(self, conn, purpose, kind, digest, limit, increment):
        return await (await conn.execute('SELECT * FROM security.record_login_window(%s,%s,%s,%s,%s)',
                                        (purpose, kind, digest, limit, increment))).fetchone()

    async def reset_input(self, conn, digest):
        await conn.execute('SELECT security.reset_login_input_window(%s)', (digest,))

    async def create(self, conn, user, revision, digest, csrf, old_digest):
        return await (await conn.execute('SELECT * FROM security.session_create_or_revoke(%s,%s,%s,%s,%s)',
                                        (user, revision, digest, csrf, old_digest))).fetchone()

    async def validate(self, conn, digest):
        row = await (await conn.execute('SELECT * FROM security.session_validate(%s)', (digest,))).fetchone()
        return SessionView(**row) if row else None

    async def revoke(self, conn, digest):
        row = await (await conn.execute('SELECT security.session_revoke(%s) AS confirmed', (digest,))).fetchone()
        return row['confirmed']

    async def membership(self, conn, session_id, tenant):
        return await (await conn.execute('SELECT * FROM security.current_membership(%s,%s)', (session_id, tenant))).fetchone()

    async def capabilities(self, conn, session_id, period, mode):
        return await (await conn.execute('SELECT * FROM security.session_capabilities(%s,%s,%s)',
                                        (session_id, period, mode))).fetchone()
