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
    'B0305':('PLATFORM_STOPPED',409),'B0306':('QUOTA_EXCEEDED',409),'B0311':('METADATA_CONFLICT',409),'B0312':('CONVERSATION_BUSY',409),'B0313':('CONVERSATION_DELETED',409)}


def request_fingerprint(agent,conversation,prompt,refs=None):
    # Original prompt and original nullable conversation stay unchanged across retries.
    data={'agent_key':agent,'conversation_id':str(conversation) if conversation else None,'prompt':prompt,'document_refs':[{k:str(v) for k,v in x.items()} for x in (refs or [])]}
    return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).digest()


class ConversationRepository:
    def __init__(self,pool):self.pool=pool

    async def read(self,ctx,kind,target,cursor,limit,digest,query="",pinned=None):
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                window=await (await conn.execute('SELECT * FROM security.run_read_window(%s,%s,%s)',
                    (ctx.session_id,ctx.tenant_id,digest))).fetchone()
                row=None
                if window['allowed']:
                    if kind=='conversations':
                        row=await (await conn.execute('SELECT security.conversation_list(%s,%s,%s,%s,%s,%s) AS data',
                            (ctx.session_id,ctx.tenant_id,query,pinned,Jsonb(cursor) if cursor is not None else None,limit))).fetchone()
                    else:
                        row=await (await conn.execute('SELECT security.run_read(%s,%s,%s,%s,%s,%s) AS data',
                            (ctx.session_id,ctx.tenant_id,kind,target,Jsonb(cursor) if cursor is not None else None,limit))).fetchone()
            if not window['allowed']:raise AppError('RATE_LIMITED',429,window['retry_after'])
            return row['data']
        except (psycopg.Error,ValueError) as error:self.translate(error)

    async def mutate(self,ctx,target,delta,revision,delete,request_id):
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                row=await (await conn.execute('SELECT security.conversation_mutate(%s,%s,%s,%s,%s,%s,%s) AS data',
                    (ctx.session_id,ctx.tenant_id,target,Jsonb(delta),revision,delete,request_id))).fetchone()
            return row['data']
        except (psycopg.Error,ValueError) as error:self.translate(error)

    async def create(self,ctx,agent,client_id,request_id):
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                row=await (await conn.execute('SELECT security.conversation_create(%s,%s,%s,%s,%s) AS data',
                    (ctx.session_id,ctx.tenant_id,agent,client_id,request_id))).fetchone()
            return row['data']
        except (psycopg.Error,ValueError) as error:self.translate(error)

    async def admit(self,ctx,agent,conversation,send,prompt,period,mode,digest,request_id,refs=None,documents=None,asset_id=None):
        fingerprint=request_fingerprint(agent,conversation,prompt,refs)
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                await conn.execute('SELECT security.run_asset_resolve(%s,%s,%s,%s)',
                    (ctx.session_id,ctx.tenant_id,agent,asset_id))
                if agent=='rules_rag':
                    if documents is None:raise AppError('FEATURE_NOT_READY',409)
                    from app.documents.search import SearchRepository
                    await conn.execute("SELECT set_config('app.rag_refs',%s,true)",(json.dumps([{k:str(v) for k,v in x.items()} for x in (refs or [])]),))
                ready=(await (await conn.execute('SELECT security.run_prepare(%s,%s,%s,%s,%s,%s,%s,%s) AS data',
                    (ctx.session_id,ctx.tenant_id,agent,conversation,send,fingerprint,period,mode))).fetchone())['data']
                if 'replay' in ready:return ready['replay']
                if agent=='rules_rag':
                    sources=await SearchRepository(documents).allowed(ctx,refs,mode,conn)
                    await conn.execute('SELECT security.rag_sources_guard(%s,%s,%s,%s)',(ctx.session_id,ctx.tenant_id,mode,Jsonb(list(sources))))
                history=[{'role':m['role'],'content':m['content']} for m in ready['history']] if agent=='general' else []
                try:
                    selected=validate_general_input(ready['instructions'],history,prompt)
                    token_count=general_token_count(selected)
                    if agent=='rules_rag' and token_count>4000:raise ValueError('INPUT_TOKEN_LIMIT')
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

    async def get_context_for_regeneration(self,ctx,conversation_id,message_id):
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                row=await (await conn.execute(
                    """
                    SELECT m_user.body AS prompt,
                           r.agent_key,
                           r.asset_id,
                           r.config_snapshot->'document_refs' AS document_refs
                    FROM portal.messages m_assist
                    JOIN portal.runs r ON r.tenant_id = m_assist.tenant_id AND r.run_id = m_assist.run_id
                    JOIN portal.messages m_user ON m_user.tenant_id = m_assist.tenant_id
                                                AND m_user.conversation_id = m_assist.conversation_id
                                                AND m_user.run_id = m_assist.run_id
                                                AND m_user.role = 'user'
                    WHERE m_assist.tenant_id = %s
                      AND m_assist.conversation_id = %s
                      AND m_assist.message_id = %s
                      AND m_assist.role = 'assistant'
                    """,
                    (ctx.tenant_id,conversation_id,message_id)
                )).fetchone()
                if not row:raise AppError('MESSAGE_NOT_FOUND',404)
                return dict(row)
        except (psycopg.Error,ValueError) as error:self.translate(error)

    @staticmethod
    def translate(error):
        if isinstance(error,psycopg.Error) and error.sqlstate in SQL_ERRORS:
            code,status=SQL_ERRORS[error.sqlstate];raise AppError(code,status) from None
        OperationsRepository.translate(error)
