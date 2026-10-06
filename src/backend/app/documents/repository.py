"""Server-scoped document control; filesystem additions and DB commit stay separate."""
import hashlib
import hmac
import json
from uuid import UUID
import psycopg
from psycopg.types.json import Jsonb
from app.db import tenant_transaction
from app.errors import AppError
from app.auth.crypto import window_digest
from app.documents.storage import validate_source,SourceStorageError,StoredSource
from app.documents.plan import build_document_plan
from common_core.ai_pipeline.document.schemas import DocumentMetadata
from common_core.ai_pipeline.document.parser import parse_source


def request_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).digest()


def scoped_id(secret,ctx,client,kind):
    value=hmac.new(secret.encode(),f'{ctx.tenant_id}:{ctx.user_id}:{client}:{kind}'.encode(),hashlib.sha256).digest()[:16]
    return UUID(bytes=value,version=5)


class DocumentRepository:
    def __init__(self,pool,storage,secret,mode='mock'):
        self.pool=pool;self.storage=storage;self.secret=secret;self.mode=mode

    async def rpc(self,ctx,name,args,trace_request=None):
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                data=(await (await conn.execute('SELECT security.'+name+'('+','.join(['%s']*len(args))+') AS data',args)).fetchone())['data']
                if trace_request is not None:
                    view=(await (await conn.execute('SELECT security.document_job_control(%s,%s,%s,%s,%s,%s,%s) AS data',(ctx.session_id,ctx.tenant_id,UUID(data['job_id']),'view',None,None,Jsonb({})))).fetchone())['data']
                    doc=UUID(view['document_id'])
                    await conn.execute('SELECT security.document_request_trace(%s,%s,%s,%s,%s)',(ctx.session_id,ctx.tenant_id,trace_request,doc,UUID(data['job_id'])))
                return data
        except (psycopg.Error,ValueError) as e:
            raise self.error(e) from None

    @staticmethod
    def error(e):
        if isinstance(e,ValueError):return AppError('AUTH_REQUIRED',401)
        return AppError(*{'A0404':('DOCUMENT_UNAVAILABLE',404),'A0409':('REVISION_CONFLICT',409),'A0403':('MANAGEMENT_DENIED',403),'A0401':('AUTH_REQUIRED',401),'A0422':('REQUEST_INVALID',422),'B0401':('EXECUTION_FENCED',409),'B0402':('AGENT_DISABLED',409)}.get(getattr(e,'sqlstate',None),('STORAGE_UNAVAILABLE',503)))

    async def register(self,ctx,metadata,content,document_id=None,request_id=None,*,personal=False):
        prefix="user_" if personal else ""
        if personal:
            if document_id is not None or set(metadata)-{"client_upload_id","title","media_type"}:raise AppError("REQUEST_INVALID",422)
            metadata={**metadata,"visibility":"private","owner_user_id":ctx.user_id,"reader_ids":[]}
        try:text=validate_source(content,metadata['title'],metadata['media_type'])
        except SourceStorageError:raise AppError('SOURCE_INVALID',422) from None
        client=metadata['client_upload_id'];doc=document_id or scoped_id(self.secret,ctx,client,'document')
        version=scoped_id(self.secret,ctx,client,'version');index=scoped_id(self.secret,ctx,client,'index');job=scoped_id(self.secret,ctx,client,'job')
        source_sha=hashlib.sha256(content).digest()
        expected=metadata.get('expected_revision');visibility=metadata.get('visibility','org');owner=metadata.get('owner_user_id') or ctx.user_id;readers=metadata.get('reader_ids',[])
        digest=request_digest({'metadata':{k:str(v) if isinstance(v,UUID) else [str(x) for x in v] if isinstance(v,list) else v for k,v in metadata.items()},'document_id':str(document_id) if document_id else None,'source_sha256':source_sha.hex(),'mode':self.mode})
        digest=hmac.new(self.secret.encode(),digest,hashlib.sha256).digest()
        try:
            source=parse_source(content,metadata['media_type'])
            plan=build_document_plan(content,metadata['title'],metadata['media_type'],DocumentMetadata(ctx.tenant_id,doc,version,index,source_sha,self.mode))
        except ValueError:raise AppError('SOURCE_INVALID',422) from None
        mapping={'revision':source.parser_revision,'offset_unit':'unicode_codepoint','mapping':source.mapping,'lines':[{'start':x.start,'end':x.end,'kind':x.kind} for x in source.lines]}
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                replayed=(await (await conn.execute('SELECT security.'+prefix+'document_upload_preflight(%s,%s,%s,%s,%s,%s) AS replayed',(ctx.session_id,ctx.tenant_id,client,digest,document_id,expected))).fetchone())['replayed']
                if not replayed:
                    window=window_digest(self.secret,'document_admission','principal',str(ctx.user_id)+':'+str(ctx.tenant_id))
                    admission=await (await conn.execute('SELECT * FROM security.'+prefix+'document_admission_window(%s,%s,%s)',(ctx.session_id,ctx.tenant_id,window))).fetchone()
                    if not admission['allowed']:raise AppError('RATE_LIMITED',429,admission['retry_after'])
                await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(str(ctx.tenant_id)+str(ctx.user_id)+str(client),))
                await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'tenants/{ctx.tenant_id}/documents/{doc}/{version}/source',))
                # Write only after current authorization. Same key never overwrites.
                try:self.storage.write(ctx.tenant_id,doc,version,content,metadata['title'],metadata['media_type'])
                except SourceStorageError as e:
                    if str(e)!='SOURCE_ALREADY_EXISTS':raise
                    self.storage.read(StoredSource(f'tenants/{ctx.tenant_id}/documents/{doc}/{version}/source',source_sha,len(content),len(text),metadata['title'],metadata['media_type']))
                args=(ctx.session_id,ctx.tenant_id,client,digest,doc,version,index,job,document_id is not None,expected,owner,visibility,readers,metadata['title'],metadata['media_type'],source_sha,len(content),len(text),bytes.fromhex(plan.source_fingerprint),self.mode,Jsonb(mapping))
                row=await (await conn.execute('SELECT security.'+prefix+'document_register('+','.join(['%s']*len(args))+') AS data',args)).fetchone()
                result=row['data']
                if request_id is not None:
                    await conn.execute('SELECT security.'+prefix+'document_request_trace(%s,%s,%s,%s,%s)',(ctx.session_id,ctx.tenant_id,request_id,UUID(result['document_id']),UUID(result['job_id'])))
            return result
        except SourceStorageError:raise AppError('SOURCE_CONFLICT',409) from None
        except (psycopg.Error,ValueError) as e:raise self.error(e) from None
        # A commit-uncertain file remains private; same-ID recovery checks DB and immutable bytes.

    async def listing(self,ctx,kind,cursor,limit):
        await self.read_window(ctx)
        return await self.rpc(ctx,'document_admin_list',(ctx.session_id,ctx.tenant_id,kind,cursor,limit))

    async def personal_listing(self,ctx,kind,cursor,limit):
        await self.read_window(ctx)
        return await self.rpc(ctx,'user_document_list',(ctx.session_id,ctx.tenant_id,kind,cursor,limit))

    async def personal_job(self,ctx,job_id):
        await self.read_window(ctx)
        return await self.rpc(ctx,'user_document_job_view',(ctx.session_id,ctx.tenant_id,job_id))

    async def job(self,ctx,job_id,action='view',epoch=None,claim=None,data=None):
        if action=='view':await self.read_window(ctx)
        if action=='claim':data={**(data or {}),'mode':self.mode}
        return await self.rpc(ctx,'document_job_control',(ctx.session_id,ctx.tenant_id,job_id,action,epoch,claim,Jsonb(data or {})))

    async def delete(self,ctx,document_id,revision,request_id=None,*,personal=False):
        prefix="user_" if personal else ""
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                result=(await (await conn.execute('SELECT security.'+prefix+'document_delete(%s,%s,%s,%s) AS data',(ctx.session_id,ctx.tenant_id,document_id,revision))).fetchone())['data']
                if request_id is not None:
                    await conn.execute('SELECT security.'+prefix+'document_request_trace(%s,%s,%s,%s,%s)',(ctx.session_id,ctx.tenant_id,request_id,document_id,None))
            return result
        except (psycopg.Error,ValueError) as e:raise self.error(e) from None

    async def cleanup_orphans(self, ctx):
        # Confirm authorization before inventory. Unknown DB result retains every file.
        await self.rpc(ctx,'document_manage',(ctx.session_id,ctx.tenant_id,False))
        removed=0
        for key in self.storage.source_keys(ctx.tenant_id):
            parts=key.split('/')
            async with tenant_transaction(self.pool,ctx) as conn:
                allowed=(await (await conn.execute('SELECT security.document_orphan_absent(%s,%s,%s,%s) AS allowed',(ctx.session_id,ctx.tenant_id,UUID(parts[3]),UUID(parts[4])))).fetchone())['allowed']
                if allowed:removed+=self.storage.remove(key,minimum_age_seconds=60)
        return removed

    async def read_window(self,ctx):
        window=window_digest(self.secret,'http_read','principal',str(ctx.user_id)+':'+str(ctx.tenant_id))
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                row=await (await conn.execute('SELECT * FROM security.run_read_window(%s,%s,%s)',(ctx.session_id,ctx.tenant_id,window))).fetchone()
        except (psycopg.Error,ValueError) as e:raise self.error(e) from None
        if not row['allowed']:raise AppError('RATE_LIMITED',429,row['retry_after'])
