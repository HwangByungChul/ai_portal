import psycopg
from psycopg.types.json import Jsonb
from app.db import tenant_transaction
from app.errors import AppError
from app.tenants.repository import TenantRepository


class CatalogRepository:
    def __init__(self, pool): self.pool = pool

    async def call(self, ctx, action, asset_id=None, agent=None, body=None, period=None, mode=None, trace=None, digest=None):
        try:
            async with tenant_transaction(self.pool, ctx) as conn:
                window = None
                if digest is not None:
                    if action in ('access_get', 'access_set', 'members'):
                        window = await (await conn.execute('SELECT * FROM security.operations_read_window(%s,%s,%s,%s)', (ctx.session_id,ctx.tenant_id,'agent_admin',digest))).fetchone()
                    else:
                        window = await (await conn.execute('SELECT * FROM security.run_read_window(%s,%s,%s)', (ctx.session_id,ctx.tenant_id,digest))).fetchone()
                result = None
                if window is None or window['allowed']:
                    if action in ('favorite','access_set'):
                        row = await (await conn.execute('SELECT security.catalog_write(%s,%s,%s,%s,%s,%s,%s) AS data', (ctx.session_id,ctx.tenant_id,action,asset_id,agent,Jsonb(body or {}),trace))).fetchone()
                    else:
                        row = await (await conn.execute('SELECT security.catalog_read(%s,%s,%s,%s,%s,%s,%s) AS data', (ctx.session_id,ctx.tenant_id,action,asset_id,Jsonb(body or {}),period,mode))).fetchone()
                    result = row['data']
            if window is not None and not window['allowed']: raise AppError('RATE_LIMITED',429,window['retry_after'])
            return result
        except (psycopg.Error, ValueError) as error:
            if isinstance(error,psycopg.Error) and error.sqlstate in ('22P02','22003','22021','22P05'): raise AppError('REQUEST_INVALID',422) from None
            TenantRepository.translate(error)
