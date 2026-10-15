import psycopg
from psycopg.types.json import Jsonb
from app.db import tenant_transaction
from app.errors import AppError
from app.tenants.repository import TenantRepository


class AssetRepository:
    def __init__(self, pool):
        self.pool = pool

    async def call(self, ctx, action, asset_id, body, trace=None, digest=None):
        try:
            async with tenant_transaction(self.pool, ctx) as conn:
                window = None
                if digest is not None:
                    window = await (await conn.execute(
                        'SELECT * FROM security.operations_read_window(%s,%s,%s,%s)',
                        (ctx.session_id, ctx.tenant_id, 'agent_admin', digest))).fetchone()
                result = None
                if window is None or window['allowed']:
                    row = await (await conn.execute(
                        'SELECT security.asset_registry(%s,%s,%s,%s,%s,%s) AS data',
                        (ctx.session_id, ctx.tenant_id, action, asset_id, Jsonb(body), trace))).fetchone()
                    result = row['data']
            if window is not None and not window['allowed']:
                raise AppError('RATE_LIMITED', 429, window['retry_after'])
            return result
        except (psycopg.Error, ValueError) as error:
            if isinstance(error, psycopg.Error):
                if error.sqlstate == 'D0410':
                    raise AppError('BUILDER_PROFILE_REQUIRED', 409) from None
                if error.sqlstate == 'D0409':
                    raise AppError('ASSET_LEGACY_READ_ONLY', 409) from None
                if error.sqlstate == 'D0429':
                    raise AppError('ASSET_LIMIT_REACHED', 409) from None
                if error.sqlstate in ('22P02', '22003', '22021', '22P05'):
                    raise AppError('REQUEST_INVALID', 422) from None
            TenantRepository.translate(error)
