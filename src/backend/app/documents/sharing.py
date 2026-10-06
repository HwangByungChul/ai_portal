"""Current allowed versions and owner-only exact-version sharing."""
from uuid import UUID
from app.db import tenant_transaction
from app.errors import AppError
from app.documents.cursor import decode_cursor,encode_cursor

class SharingRepository:
    def __init__(self,documents):self.documents=documents
    async def control(self,ctx,document=None,version=None,action='list',recipient=None,grant=None,expected=None,request=None):
        return await self.documents.rpc(ctx,'document_share_control',(ctx.session_id,ctx.tenant_id,document,version,action,recipient,grant,expected,request))
    async def targets(self,ctx):
        await self.documents.read_window(ctx)
        return await self.documents.rpc(ctx,'document_share_targets',(ctx.session_id,ctx.tenant_id))
    async def readable(self,ctx,cursor,limit,scope=None):
        await self.documents.read_window(ctx)
        position=decode_cursor(self.documents.secret,ctx,'readable',cursor)
        async with tenant_transaction(self.documents.pool,ctx) as conn:
            rows=await (await conn.execute('''SELECT v.tenant_id AS source_tenant_id,v.document_id,v.version_id,v.version_no,v.title,security.document_read_visibility(v.tenant_id,v.document_id,v.version_id) AS visibility,'v'||v.version_no::text AS safe_version_label,i.index_id,i.execution_mode FROM rag.document_versions v JOIN rag.index_builds i ON (i.tenant_id,i.document_id,i.version_id)=(v.tenant_id,v.document_id,v.version_id) WHERE security.document_can_read(v.tenant_id,v.document_id,v.version_id,i.index_id) AND (%s::uuid IS NULL OR v.version_id>%s) AND (%s::text IS NULL OR security.document_read_visibility(v.tenant_id,v.document_id,v.version_id)=%s) ORDER BY v.version_id LIMIT %s''',(position,position,scope,scope,limit+1))).fetchall()
        more=len(rows)>limit;rows=rows[:limit]
        public=[{k:str(v) if isinstance(v,UUID) else v for k,v in row.items()} for row in rows]
        return {'items':public,'next_cursor':encode_cursor(self.documents.secret,ctx,'readable',rows[-1]['version_id']) if more else None}
