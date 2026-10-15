import psycopg
from psycopg.types.json import Jsonb
from app.db import tenant_transaction
from app.errors import AppError
from app.tenants.repository import TenantRepository


class ApprovalRepository:
    def __init__(self, pool):
        self.pool = pool

    async def call(self, ctx, action, request_id, body, period, mode, trace=None, digest=None):
        try:
            async with tenant_transaction(self.pool, ctx) as conn:
                if digest is not None:
                    window = await (await conn.execute(
                        'SELECT * FROM security.operations_read_window(%s,%s,%s,%s)',
                        (ctx.session_id, ctx.tenant_id, 'agent_admin', digest))).fetchone()
                    if not window['allowed']:
                        # Commit the shared read limiter before surfacing its rejection.
                        result = None
                    else:
                        result = await self._execute(conn, ctx, action, request_id, body, period, mode, trace)
                else:
                    window = None
                    result = await self._execute(conn, ctx, action, request_id, body, period, mode, trace)
            if window is not None and not window['allowed']:
                raise AppError('RATE_LIMITED', 429, window['retry_after'])
            return result
        except psycopg.Error as error:
            if error.sqlstate == 'D0429':
                raise AppError('DEPLOYMENT_QUEUE_FULL', 409) from None
            if error.sqlstate in ('22P02', '22003'):
                raise AppError('REQUEST_INVALID', 422) from None
            TenantRepository.translate(error)

    @staticmethod
    async def _execute(conn, ctx, action, request_id, body, period, mode, trace):
        row = await (await conn.execute(
            'SELECT security.agent_deployment(%s,%s,%s,%s,%s,%s,%s,%s) AS data',
            (ctx.session_id, ctx.tenant_id, action, request_id, Jsonb(body), period, mode, trace))).fetchone()
        return row['data']
