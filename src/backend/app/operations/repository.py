from contextlib import asynccontextmanager
import psycopg
from psycopg.types.json import Jsonb
from app.db import tenant_transaction
from app.errors import AppError
from app.tenants.repository import TenantRepository


@asynccontextmanager
async def operation_transaction(pool,ctx):
    if ctx.tenant_id is not None:
        async with tenant_transaction(pool,ctx) as conn:
            yield conn
    else:
        async with pool.connection() as conn:
            async with conn.transaction():
                for key,value in [('app.user_id',ctx.user_id),('app.session_id',ctx.session_id),('app.tenant_id','')]:
                    await conn.execute('SELECT set_config(%s,%s,true)',(key,str(value)))
                yield conn


class OperationsRepository:
    def __init__(self,pool):self.pool=pool

    async def read(self,ctx,kind,period,mode,digest,agent=None,cursor=None,limit=20):
        try:
            async with operation_transaction(self.pool,ctx) as conn:
                window=await (await conn.execute('SELECT * FROM security.operations_read_window(%s,%s,%s,%s)',
                    (ctx.session_id,ctx.tenant_id,kind,digest))).fetchone()
                row=await (await conn.execute('SELECT security.operations_read(%s,%s,%s,%s,%s,%s,%s,%s) AS data',
                    (ctx.session_id,ctx.tenant_id,kind,period,mode,agent,cursor,limit))).fetchone() if window['allowed'] else None
            if not window['allowed']:raise AppError('RATE_LIMITED',429,window['retry_after'])
            return row['data']
        except (psycopg.Error,ValueError) as error:self.translate(error)

    async def mutate(self,ctx,kind,period,mode,delta,revision,request_id,agent=None):
        try:
            async with operation_transaction(self.pool,ctx) as conn:
                row=await (await conn.execute('SELECT security.operations_mutate(%s,%s,%s,%s,%s,%s,%s,%s,%s) AS data',
                    (ctx.session_id,ctx.tenant_id,kind,period,mode,agent,Jsonb(delta),revision,request_id))).fetchone()
            return row['data']
        except (psycopg.Error,ValueError) as error:self.translate(error)

    @staticmethod
    def translate(error):
        if isinstance(error,psycopg.Error) and error.sqlstate=='D0409':
            raise AppError('APPROVAL_REQUIRED',409) from None
        if isinstance(error,psycopg.Error) and error.sqlstate in ('B0209','B0210'):
            raise AppError('BUDGET_LIMIT_CONFLICT' if error.sqlstate=='B0209' else 'REVIEW_REQUIRED',409) from None
        TenantRepository.translate(error)
