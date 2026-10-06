from uuid import UUID
from typing import Literal
from fastapi import APIRouter,Request,Query
from pydantic import BaseModel,ConfigDict
from app.operations.routes import Revision,validate_query
from app.tenants.routes import context
from app.errors import response
from app.documents.sharing import SharingRepository

router=APIRouter(prefix='/api/v1')
class GrantRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    recipient_tenant_id:UUID
    expected_publication_revision:Revision
class RevokeRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision:Revision

def repository(request):return SharingRepository(request.app.state.documents)
@router.get('/documents')
async def readable(request:Request,cursor:str|None=None,limit:int=Query(default=20,ge=1,le=50),scope:Literal['org','private','shared']|None=None):
    ctx=await context(request);validate_query(request,{'cursor','limit','scope'})
    return response(request,await repository(request).readable(ctx,cursor,limit,scope))
@router.get('/admin/share-recipients')
async def targets(request:Request):
    ctx=await context(request);validate_query(request,set());return response(request,await repository(request).targets(ctx))
@router.get('/admin/documents/{document_id}/versions/{version_id}/grants')
async def grants(request:Request,document_id:UUID,version_id:UUID):
    ctx=await context(request);validate_query(request,set());await request.app.state.documents.read_window(ctx)
    return response(request,await repository(request).control(ctx,document_id,version_id))
@router.post('/admin/documents/{document_id}/versions/{version_id}/grants')
async def issue(request:Request,document_id:UUID,version_id:UUID,body:GrantRequest):
    ctx=await context(request,write=True);validate_query(request,set())
    data=await repository(request).control(ctx,document_id,version_id,'issue',body.recipient_tenant_id,expected=body.expected_publication_revision,request=UUID(request.state.request_id))
    return response(request,data,status_code=200 if data['replayed'] else 201)
@router.delete('/admin/grants/{grant_id}')
async def revoke(request:Request,grant_id:UUID,body:RevokeRequest):
    ctx=await context(request,write=True);validate_query(request,set())
    return response(request,await repository(request).control(ctx,action='revoke',grant=grant_id,expected=body.expected_revision,request=UUID(request.state.request_id)))
