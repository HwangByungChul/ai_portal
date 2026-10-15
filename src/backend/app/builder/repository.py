import psycopg
from psycopg.types.json import Jsonb
from app.db import tenant_transaction
from app.errors import AppError
from app.tenants.repository import TenantRepository


class BuilderRepository:
    def __init__(self,pool):self.pool=pool

    async def call(self,ctx,action,asset=None,version=None,body=None,trace=None,digest=None):
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                window=None
                if digest is not None:
                    window=await (await conn.execute('SELECT * FROM security.operations_read_window(%s,%s,%s,%s)',(ctx.session_id,ctx.tenant_id,'agent_admin',digest))).fetchone()
                result=None
                if window is None or window['allowed']:
                    if action=='version':
                        row=await (await conn.execute('SELECT security.builder_version(%s,%s,%s,%s) AS data',(ctx.session_id,ctx.tenant_id,asset,version))).fetchone()
                    else:
                        row=await (await conn.execute('SELECT security.builder_save(%s,%s,%s,%s,%s,%s) AS data',(ctx.session_id,ctx.tenant_id,action,asset,Jsonb(body),trace))).fetchone()
                    result=row['data']
            if window is not None and not window['allowed']:raise AppError('RATE_LIMITED',429,window['retry_after'])
            return result
        except (psycopg.Error,ValueError) as error:
            if isinstance(error,psycopg.Error):
                mapping={'D0404':('DOCUMENT_UNAVAILABLE',404),'D0410':('BUILDER_PROFILE_REQUIRED',409),'D0429':('ASSET_LIMIT_REACHED',409),'D0409':('ASSET_LEGACY_READ_ONLY',409)}
                if error.sqlstate in mapping:raise AppError(*mapping[error.sqlstate]) from None
                if error.sqlstate in ('22P02','22003','22021','22P05'):raise AppError('REQUEST_INVALID',422) from None
            TenantRepository.translate(error)
