"""Fixed bound SQL, offline token validation and transactional intake."""
import hashlib
import json
from uuid import UUID
import psycopg
from psycopg.types.json import Jsonb
from app.ai.token_limits import TokenizerNotReady,general_token_count,validate_general_input
from app.db import tenant_transaction
from app.errors import AppError
from app.operations.repository import OperationsRepository

SQL_ERRORS={'B0301':('SEND_ID_CONFLICT',409),'B0302':('CONVERSATION_AGENT_MISMATCH',409),
    'B0303':('AGENT_STOPPED',409),'B0304':('FEATURE_NOT_READY',409),
    'B0305':('PLATFORM_STOPPED',409),'B0306':('QUOTA_EXCEEDED',409)}


def request_fingerprint(agent,conversation,prompt):
    # Original prompt and original nullable conversation stay unchanged across retries.
    data={'agent_key':agent,'conversation_id':str(conversation) if conversation else None,'prompt':prompt,'document_refs':[]}
    return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).digest()


class ConversationRepository:
    def __init__(self,pool):self.pool=pool

    async def read(self,ctx,kind,target,cursor,limit,digest):
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                window=await (await conn.execute('SELECT * FROM security.run_read_window(%s,%s,%s)',
                    (ctx.session_id,ctx.tenant_id,digest))).fetchone()
                row=await (await conn.execute('SELECT security.run_read(%s,%s,%s,%s,%s,%s) AS data',
                    (ctx.session_id,ctx.tenant_id,kind,target,Jsonb(cursor) if cursor is not None else None,limit))).fetchone() if window['allowed'] else None
            if not window['allowed']:raise AppError('RATE_LIMITED',429,window['retry_after'])
            return row['data']
        except (psycopg.Error,ValueError) as error:self.translate(error)

    async def create(self,ctx,agent,client_id,request_id):
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                row=await (await conn.execute('SELECT security.conversation_create(%s,%s,%s,%s,%s) AS data',
                    (ctx.session_id,ctx.tenant_id,agent,client_id,request_id))).fetchone()
            return row['data']
        except (psycopg.Error,ValueError) as error:self.translate(error)

    async def admit(self,ctx,agent,conversation,send,prompt,period,mode,digest,request_id):
        fingerprint=request_fingerprint(agent,conversation,prompt)
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                ready=(await (await conn.execute('SELECT security.run_prepare(%s,%s,%s,%s,%s,%s,%s,%s) AS data',
                    (ctx.session_id,ctx.tenant_id,agent,conversation,send,fingerprint,period,mode))).fetchone())['data']
                if 'replay' in ready:return ready['replay']
                history=[{'role':m['role'],'content':m['content']} for m in ready['history']]
                try:
                    selected=validate_general_input(ready['instructions'],history,prompt)
                    token_count=general_token_count(selected)
                except TokenizerNotReady:raise AppError('SERVICE_UNAVAILABLE',503) from None
                except ValueError:raise AppError('TOKEN_LIMIT_EXCEEDED',422) from None
                count=len(selected)-2
                selected_ids=[UUID(m['message_id']) for m in ready['history'][-count:]] if count else []
                row=await (await conn.execute('SELECT security.run_admit(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) AS data',
                    (ctx.session_id,ctx.tenant_id,agent,conversation,send,fingerprint,prompt,period,mode,
                     ready['config_version'],selected_ids,token_count,digest,request_id))).fetchone()
            data=row['data']
            if 'admission_error' in data:raise AppError(data['admission_error'],429,data['retry_after'])
            return data
        except (psycopg.Error,ValueError) as error:self.translate(error)

    async def cancel(self,ctx,run,revision,request_id):
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                row=await (await conn.execute('SELECT security.run_cancel(%s,%s,%s,%s,%s) AS data',
                    (ctx.session_id,ctx.tenant_id,run,revision,request_id))).fetchone()
            return row['data']
        except (psycopg.Error,ValueError) as error:self.translate(error)

    @staticmethod
    def translate(error):
        if isinstance(error,psycopg.Error) and error.sqlstate in SQL_ERRORS:
            code,status=SQL_ERRORS[error.sqlstate];raise AppError(code,status) from None
        OperationsRepository.translate(error)
