from uuid import UUID
from fastapi import APIRouter,Request,Query
from pydantic import BaseModel,ConfigDict,StrictInt,Field
from app.auth.guards import check_write,check_transport,cookie_token,check_csrf
from app.errors import AppError,response
from app.documents.upload import parse_upload
from app.documents.cursor import encode_cursor,decode_cursor
from app.documents.repository import request_digest,scoped_id

router=APIRouter(prefix='/api/v1/admin')
class RevisionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision:StrictInt=Field(ge=1,le=9223372036854775807)
class RetryRequest(RevisionRequest):client_retry_id:UUID

async def context(request,write=False,json_body=True):
    s=request.app.state.settings;auth=request.app.state.auth
    if write:check_write(request,s,json_body=json_body)
    else:check_transport(request,s)
    token=cookie_token(request,s);session=await auth.validate(token)
    if write:check_csrf(request,session.csrf_secret)
    values=request.headers.getlist('x-tenant-id')
    if len(values)!=1:raise AppError('REQUEST_INVALID',422)
    try:tenant=UUID(values[0])
    except ValueError:raise AppError('REQUEST_INVALID',422) from None
    ctx=await auth.resolve_tenant(token,tenant);request.state.tenant_id=str(tenant);return ctx

def repository(request):return request.app.state.documents

@router.get('/documents')
async def documents(request:Request,cursor:str|None=None,limit:int=Query(default=20,ge=1,le=50)):
    ctx=await context(request);repo=repository(request)
    if any(len(request.query_params.getlist(k))>1 for k in ('cursor','limit')):raise AppError('REQUEST_INVALID',422)
    data=await repo.listing(ctx,'documents',decode_cursor(repo.secret,ctx,'documents',cursor),limit)
    data['next_cursor']=encode_cursor(repo.secret,ctx,'documents',data['next_cursor'])
    return response(request,data)

async def upload(request,document=None):
    ctx=await context(request,True,False)
    if len(request.headers.getlist('content-type'))!=1:raise AppError('REQUEST_INVALID',422)
    meta,raw=parse_upload(await request.body(),request.headers['content-type'],document is not None)
    data=await repository(request).register(ctx,meta,raw,document)
    manager=request.app.state.document_manager
    if manager:manager.notify(ctx,UUID(data['job_id']))
    return response(request,data,status_code=202)

@router.post('/documents')
async def new_document(request:Request):return await upload(request)
@router.post('/documents/{document_id}/versions')
async def new_version(request:Request,document_id:UUID):return await upload(request,document_id)
@router.delete('/documents/{document_id}')
async def delete_document(request:Request,document_id:UUID,body:RevisionRequest):
    ctx=await context(request,True);data=await repository(request).delete(ctx,document_id,body.expected_revision)
    manager=request.app.state.document_manager
    if manager:
        manager.notify(ctx,document_id,'internal_cleanup',document_id)
    return response(request,data)
@router.get('/jobs')
async def jobs(request:Request,cursor:str|None=None,limit:int=Query(default=20,ge=1,le=50)):
    ctx=await context(request);repo=repository(request)
    if any(len(request.query_params.getlist(k))>1 for k in ('cursor','limit')):raise AppError('REQUEST_INVALID',422)
    data=await repo.listing(ctx,'jobs',decode_cursor(repo.secret,ctx,'jobs',cursor),limit)
    data['next_cursor']=encode_cursor(repo.secret,ctx,'jobs',data['next_cursor'])
    return response(request,data)
@router.get('/jobs/{job_id}')
async def job(request:Request,job_id:UUID):
    ctx=await context(request);return response(request,await repository(request).job(ctx,job_id))
@router.post('/jobs/{job_id}/retry')
async def retry(request:Request,job_id:UUID,body:RetryRequest):
    ctx=await context(request,True);repo=repository(request)
    digest=request_digest({'job':str(job_id),'client':str(body.client_retry_id),'revision':body.expected_revision})
    new_job=scoped_id(repo.secret,ctx,body.client_retry_id,'retry')
    data=await repo.rpc(ctx,'document_retry',(ctx.session_id,ctx.tenant_id,job_id,body.client_retry_id,body.expected_revision,digest,new_job,repo.mode))
    manager=request.app.state.document_manager
    if manager:manager.notify(ctx,UUID(data['job_id']))
    return response(request,data,status_code=202)
