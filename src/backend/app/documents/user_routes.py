"""Owner-private control routes; readable published documents retain their own API."""
from uuid import UUID
from fastapi import APIRouter,Request,Query
from app.errors import AppError,response
from app.documents.routes import context,repository,RevisionRequest
from app.documents.upload import parse_upload
from app.documents.cursor import encode_cursor,decode_cursor
from app.operations.routes import validate_query
router=APIRouter(prefix='/api/v1')

@router.post('/documents')
async def upload(request:Request):
    ctx=await context(request,True,False);validate_query(request,set())
    if len(request.headers.getlist('content-type'))!=1:raise AppError('REQUEST_INVALID',422)
    meta,raw=parse_upload(await request.body(),request.headers['content-type'],personal=True)
    data=await repository(request).register(ctx,meta,raw,request_id=UUID(request.state.request_id),personal=True)
    manager=request.app.state.document_manager
    if manager:manager.notify(ctx,UUID(data['job_id']))
    return response(request,data,status_code=202)

async def listing(request,kind,cursor,limit):
    ctx=await context(request);validate_query(request,{'cursor','limit'});repo=repository(request);scope='user_'+kind
    data=await repo.personal_listing(ctx,kind,decode_cursor(repo.secret,ctx,scope,cursor),limit)
    data['next_cursor']=encode_cursor(repo.secret,ctx,scope,data['next_cursor'])
    return response(request,data)

@router.get('/documents/mine')
async def mine(request:Request,cursor:str|None=None,limit:int=Query(default=20,ge=1,le=50)):
    return await listing(request,'documents',cursor,limit)

@router.get('/document-jobs')
async def jobs(request:Request,cursor:str|None=None,limit:int=Query(default=20,ge=1,le=50)):
    return await listing(request,'jobs',cursor,limit)

@router.get('/document-jobs/{job_id}')
async def job(request:Request,job_id:UUID):
    ctx=await context(request);validate_query(request,set())
    return response(request,await repository(request).personal_job(ctx,job_id))

@router.delete('/documents/{document_id}')
async def remove(request:Request,document_id:UUID,body:RevisionRequest):
    ctx=await context(request,True);validate_query(request,set())
    data=await repository(request).delete(ctx,document_id,body.expected_revision,UUID(request.state.request_id),personal=True)
    manager=request.app.state.document_manager
    if manager:manager.notify(ctx,document_id,'internal_cleanup',document_id)
    return response(request,data)
