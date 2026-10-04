"""Bound control SQL; tenant identity comes from the verified server session."""
import psycopg
from app.db import tenant_transaction
from app.errors import AppError
from app.types import TenantView,MembershipView,MemberPage

SQL_ERRORS = {'A0401': ('AUTH_REQUIRED',401), 'A0403': ('REQUEST_FORBIDDEN',403),
              'A0404': ('RESOURCE_NOT_FOUND',404), 'A0409': ('REVISION_CONFLICT',409),
              'A0422': ('REQUEST_INVALID',422)}


class TenantRepository:
    def __init__(self,pool):
        self.pool=pool

    async def own_tenants(self,session):
        async with self.pool.connection() as conn:
            rows=await (await conn.execute('SELECT * FROM security.list_own_tenants(%s)',(session.session_id,))).fetchall()
            return [TenantView(**row) for row in rows]

    async def members(self,ctx,cursor,limit,digest):
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                window=await (await conn.execute('SELECT * FROM security.record_http_read_window(%s,%s,%s)',
                    (ctx.session_id,ctx.tenant_id,digest))).fetchone()
                rows=await (await conn.execute('SELECT * FROM security.list_memberships(%s,%s,%s,%s)',
                    (ctx.session_id,ctx.tenant_id,cursor,limit))).fetchall() if window['allowed'] else []
            # Commit the read window before returning a 429.
            if not window['allowed']:
                raise AppError('RATE_LIMITED',429,window['retry_after'])
            items=[MembershipView(**row) for row in rows[:limit]]
            return MemberPage(items,items[-1].user_id if len(rows)>limit else None)
        except (psycopg.Error,ValueError) as error:
            self.translate(error)

    async def mutate(self,ctx,target,operation,active,role,revision,request_id):
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                row=await (await conn.execute('SELECT * FROM security.mutate_membership(%s,%s,%s,%s,%s,%s,%s,%s)',
                    (ctx.session_id,ctx.tenant_id,target,operation,active,role,revision,request_id))).fetchone()
            return MembershipView(**row)
        except (psycopg.Error,ValueError) as error:
            self.translate(error)

    @staticmethod
    def translate(error):
        if isinstance(error,ValueError):
            raise AppError('TENANT_FORBIDDEN',403) from None
        if error.sqlstate in SQL_ERRORS:
            code,status=SQL_ERRORS[error.sqlstate]
            raise AppError(code,status) from None
        raise error
