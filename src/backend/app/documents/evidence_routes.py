from uuid import UUID
from fastapi import APIRouter,Request,Path
from starlette.responses import Response
from app.db import tenant_transaction
from app.tenants.routes import context
from app.operations.routes import validate_query
from app.errors import response,AppError
from app.documents.storage import StoredSource,SourceStorageError
from app.documents.search import source_binding
from psycopg.types.json import Jsonb

router=APIRouter(prefix='/api/v1')
async def evidence_rows(request,ctx,run_id,conn):
    r=await (await conn.execute('SELECT agent_key,source_count,state,execution_mode FROM portal.runs WHERE tenant_id=%s AND run_id=%s',(ctx.tenant_id,run_id))).fetchone()
    if r is None:raise AppError('RESOURCE_NOT_FOUND',404)
    if r['agent_key']!='rules_rag':return r,[]
    enabled=await (await conn.execute("SELECT enabled FROM portal.agent_configs WHERE tenant_id=%s AND agent_key='rules_rag'",(ctx.tenant_id,))).fetchone()
    if enabled is None or not enabled['enabled']:return r,[]
    rows=await (await conn.execute('''SELECT e.ordinal,e.source_tenant_id,e.document_id,e.version_id,e.index_id,e.evidence_id,e.location_snapshot AS location,e.quote_snapshot AS quote,v.title,v.version_no,v.source_object_key,v.source_sha256,v.byte_length,v.character_length,v.media_type,v.source_mapping FROM portal.answer_evidence e JOIN rag.document_versions v ON (v.tenant_id,v.document_id,v.version_id,v.source_sha256)=(e.source_tenant_id,e.document_id,e.version_id,e.source_sha256) WHERE e.tenant_id=%s AND e.run_id=%s AND NOT e.payload_purged ORDER BY e.ordinal''',(ctx.tenant_id,run_id))).fetchall()
    return r,rows
@router.get('/runs/{run_id}/evidence')
async def evidence(request:Request,run_id:UUID):
    ctx=await context(request);validate_query(request,set());await request.app.state.documents.read_window(ctx)
    async with tenant_transaction(request.app.state.pool,ctx) as conn:
        r,rows=await evidence_rows(request,ctx,run_id,conn)
        by_id={x['ordinal']:x for x in rows};items=[]
        for n in range(r['source_count']):
            x=by_id.get(n)
            if x is None:items.append({'ordinal':n,'content_status':'unavailable'})
            else:items.append({k:str(x[k]) if isinstance(x[k],UUID) else x[k] for k in ('ordinal','document_id','version_id','title','version_no','location','quote')}|{'content_status':'available','source_url':f'/api/v1/runs/{run_id}/evidence/{n}/source'})
    for item in items:
        x=by_id.get(item['ordinal'])
        if x and x['source_mapping'].get('origin'):
            from app.documents.storage import validate_origin
            stored=StoredSource(x['source_object_key'],bytes(x['source_sha256']),x['byte_length'],x['character_length'],x['title'],x['media_type'],x['source_mapping'])
            try:origin=validate_origin(x['source_mapping'],stored)
            except SourceStorageError:raise AppError('STORAGE_UNAVAILABLE',503) from None
            loc=x['location'];pages=[p['page'] for p in origin['pages'] if p['start']<loc['end_offset'] and p['end']>loc['start_offset']]
            if not pages:raise AppError('STORAGE_UNAVAILABLE',503)
            item.update(source_media_type='application/pdf',page_start=min(pages),page_end=max(pages))
    return response(request,{'items':items})
@router.get('/runs/{run_id}/evidence/{ordinal}/source')
async def source(request:Request,run_id:UUID,ordinal:int=Path(ge=0,le=19)):
    ctx=await context(request);validate_query(request,set());await request.app.state.documents.read_window(ctx)
    async with tenant_transaction(request.app.state.pool,ctx) as conn:
        r,rows=await evidence_rows(request,ctx,run_id,conn)
        x=next((x for x in rows if x['ordinal']==ordinal),None)
        if x is None:raise AppError('DOCUMENT_UNAVAILABLE',404)
        allowed=(await (await conn.execute('SELECT security.can_read_rag_answer_payload(%s,%s) AS allowed',(ctx.tenant_id,run_id))).fetchone())['allowed']
        if not allowed:raise AppError('DOCUMENT_UNAVAILABLE',404)
        await conn.execute('SELECT security.rag_sources_guard(%s,%s,%s,%s)',(ctx.session_id,ctx.tenant_id,r['execution_mode'],Jsonb([source_binding(x)])))
        try:content=request.app.state.documents.storage.read(StoredSource(x['source_object_key'],bytes(x['source_sha256']),x['byte_length'],x['character_length'],x['title'],x['media_type'],x['source_mapping']))
        except SourceStorageError:raise AppError('STORAGE_UNAVAILABLE',503) from None
        stored=StoredSource(x['source_object_key'],bytes(x['source_sha256']),x['byte_length'],x['character_length'],x['title'],x['media_type'],x['source_mapping'])
        pdf=bool(x['source_mapping'].get('origin'))
        if pdf:
            try:content=request.app.state.documents.storage.read_original(stored)
            except SourceStorageError:raise AppError('STORAGE_UNAVAILABLE',503) from None
    return Response(content,media_type='application/pdf' if pdf else 'text/plain; charset=utf-8',headers={'Content-Disposition':'attachment; filename="document.pdf"' if pdf else 'attachment; filename="document.txt"','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Request-ID':request.state.request_id})
