from uuid import UUID
from typing import Literal,Annotated
from fastapi import APIRouter,Request,Path
from pydantic import BaseModel,ConfigDict,StrictInt,Field,field_validator
from starlette.responses import Response
from psycopg.types.json import Jsonb
from app.tenants.routes import context
from app.operations.routes import validate_query,Revision
from app.conversations.routes import DocumentRef,digest,CancelRequest
from app.conversations.repository import ConversationRepository
from app.execution.summary_repository import SummaryRepository,stored
from app.execution.exports import markdown_attachment, pdf_attachment
from app.documents.storage import SourceStorageError,validate_origin
from app.documents.formats import DOCX_MEDIA_TYPE,XLSX_MEDIA_TYPE
from app.db import tenant_transaction
from app.errors import AppError,response

router=APIRouter(prefix='/api/v1/document-summaries')
class SummaryRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    client_send_id:UUID
    document_ref:DocumentRef
    bullet_count:StrictInt
    @field_validator('bullet_count')
    @classmethod
    def bullets(cls,value):
        if value not in (3,5):raise ValueError('SUMMARY_COUNT_INVALID')
        return value
class RegenerateRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    client_send_id:UUID
    expected_revision:Revision

def repository(request):return SummaryRepository(request.app.state.documents)
def admission(data):return {k:data[k] for k in ('run_id','state','revision','replayed')}
def ensure_execution(request):
    manager=getattr(request.app.state,'execution',None)
    if manager is not None and (manager.closed or manager.gateway.stop_latch):raise AppError('PROJECT_STOPPED',503)
    return manager
async def read(request,ctx,run):
    await request.app.state.documents.read_window(ctx)
    return await repository(request).read(ctx,run)
@router.post('')
async def create(request:Request,body:SummaryRequest):
    ctx=await context(request,write=True);validate_query(request,set());manager=ensure_execution(request);s=request.app.state.settings
    data=await repository(request).admit(ctx,body.document_ref.model_dump(),body.bullet_count,body.client_send_id,s.budget_period,s.mode,digest(request,ctx,'run_admission'),UUID(request.state.request_id))
    if manager and not data['replayed'] and not data['is_terminal']:manager.notify(ctx,data['run_id'])
    return response(request,admission(data),status_code=200 if data['replayed'] else 201)
@router.get('/{run_id}')
async def view(request:Request,run_id:UUID):
    ctx=await context(request);validate_query(request,set());return response(request,await read(request,ctx,run_id))
@router.post('/{run_id}/regenerate')
async def regenerate(request:Request,run_id:UUID,body:RegenerateRequest):
    ctx=await context(request,write=True);validate_query(request,set());manager=ensure_execution(request);s=request.app.state.settings
    old=await repository(request).request(ctx,run_id)
    data=await repository(request).admit(ctx,old['document_ref'],old['bullet_count'],body.client_send_id,s.budget_period,s.mode,digest(request,ctx,'run_admission'),UUID(request.state.request_id),parent=run_id,expected=body.expected_revision)
    if manager and not data['replayed'] and not data['is_terminal']:manager.notify(ctx,data['run_id'])
    return response(request,admission(data),status_code=200 if data['replayed'] else 201)
@router.post('/{run_id}/cancel')
async def cancel(request:Request,run_id:UUID,body:CancelRequest):
    ctx=await context(request,write=True);validate_query(request,set());await repository(request).request(ctx,run_id)
    data=await ConversationRepository(request.app.state.pool).cancel(ctx,run_id,body.expected_revision,UUID(request.state.request_id));manager=getattr(request.app.state,'execution',None)
    if manager:manager.cancel(ctx,run_id)
    return response(request,data,status_code=200 if data['is_terminal'] else 202)
@router.get('/{run_id}/export')
async def export(request:Request,run_id:UUID,format:Literal['md','pdf']='md'):
    ctx=await context(request);validate_query(request,{'format'});data=await read(request,ctx,run_id)
    if format=='pdf':
        return pdf_attachment(data,request.state.request_id)
    return markdown_attachment(data,request.state.request_id)


@router.get('/{run_id}/pdf')
async def export_pdf(request:Request,run_id:UUID):
    ctx=await context(request);validate_query(request,set());data=await read(request,ctx,run_id)
    return pdf_attachment(data,request.state.request_id)
@router.get('/{run_id}/evidence/{ordinal}/source')
async def source(request:Request,run_id:UUID,ordinal:int=Path(ge=0,le=4)):
    ctx=await context(request);validate_query(request,set());data=await read(request,ctx,run_id)
    if data['content_status']!='final' or not any(e['ordinal']==ordinal for e in data['evidence']):raise AppError('DOCUMENT_UNAVAILABLE',404)
    async with tenant_transaction(request.app.state.pool,ctx) as conn:
        await conn.execute('SELECT security.summary_source_guard(%s,%s,%s)',(ctx.session_id,ctx.tenant_id,run_id))
        row=await (await conn.execute('SELECT v.tenant_id,v.document_id,v.version_id,v.version_no,v.title,v.source_object_key,v.source_sha256,v.media_type,v.byte_length,v.character_length,v.parser_revision,v.source_mapping,v.payload_purged FROM portal.summary_evidence e JOIN rag.document_versions v ON (v.tenant_id,v.document_id,v.version_id,v.source_sha256)=(e.source_tenant_id,e.document_id,e.version_id,e.source_sha256) WHERE e.tenant_id=%s AND e.run_id=%s AND e.ordinal=%s',(ctx.tenant_id,run_id,ordinal))).fetchone()
        if row is None:raise AppError('DOCUMENT_UNAVAILABLE',404)
        try:
            item=stored(row);content=request.app.state.documents.storage.read(item);origin=validate_origin(row['source_mapping'],item) if row['source_mapping'].get('origin') else None
            media=origin['media_type'] if origin else row['media_type']+'; charset=utf-8'
            filename='document.xlsx' if media==XLSX_MEDIA_TYPE else 'document.docx' if media==DOCX_MEDIA_TYPE else 'document.pdf' if origin else 'document.md' if row['media_type']=='text/markdown' else 'document.txt'
            if origin:content=request.app.state.documents.storage.read_original(item)
        except SourceStorageError:raise AppError('STORAGE_UNAVAILABLE',503) from None
    return Response(content,media_type=media,headers={'Content-Disposition':f'attachment; filename="{filename}"','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Request-ID':request.state.request_id})
