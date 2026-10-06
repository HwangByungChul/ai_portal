import psycopg
from psycopg.types.json import Jsonb
from app.db import tenant_transaction
from app.errors import AppError
from app.operations.repository import OperationsRepository


class FeedbackRepository:
    def __init__(self,pool):self.pool=pool

    async def read(self,ctx,run,digest):
        return await self._read(ctx,digest,'owner',run=run)

    async def summary(self,ctx,period,mode,agent,digest):
        return await self._read(ctx,digest,'summary',period=period,mode=mode,agent=agent)

    async def _read(self,ctx,digest,kind,*,run=None,period=None,mode=None,agent=None):
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                if kind=='summary':
                    window=await (await conn.execute('SELECT * FROM security.operations_read_window(%s,%s,%s,%s)',(ctx.session_id,ctx.tenant_id,'usage_admin',digest))).fetchone()
                    query='SELECT security.feedback_summary(%s,%s,%s,%s,%s) AS data';args=(ctx.session_id,ctx.tenant_id,period,mode,agent)
                else:
                    window=await (await conn.execute('SELECT * FROM security.run_read_window(%s,%s,%s)',(ctx.session_id,ctx.tenant_id,digest))).fetchone()
                    query='SELECT security.feedback_read(%s,%s,%s) AS data';args=(ctx.session_id,ctx.tenant_id,run)
                row=await (await conn.execute(query,args)).fetchone() if window['allowed'] else None
            if not window['allowed']:raise AppError('RATE_LIMITED',429,window['retry_after'])
            return row['data']
        except (psycopg.Error,ValueError) as error:self.translate(error)

    async def mutate(self,ctx,run,delta,revision,delete,request_id):
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                row=await (await conn.execute('SELECT security.feedback_mutate(%s,%s,%s,%s,%s,%s,%s) AS data',(ctx.session_id,ctx.tenant_id,run,Jsonb(delta),revision,delete,request_id))).fetchone()
            return row['data']
        except (psycopg.Error,ValueError) as error:self.translate(error)

    @staticmethod
    def translate(error):
        if isinstance(error,psycopg.Error) and error.sqlstate in ('B0411','B0412'):
            raise AppError('FEEDBACK_CONFLICT' if error.sqlstate=='B0411' else 'FEEDBACK_NOT_READY',409) from None
        OperationsRepository.translate(error)
