import hashlib,json
from uuid import UUID
from fastapi import APIRouter,Request
from app.tenants.routes import context
from app.auth.crypto import window_digest
from app.documents.search import SearchRepository
from app.errors import AppError,response
from app.builder.schemas import SaveProfile,AppendProfile,CloneProfile,ProfilePreview,compose
from app.builder.repository import BuilderRepository

router=APIRouter(prefix='/api/v1/admin/builder')


async def execute(request,action,asset=None,version=None,body=None,write=False):
    ctx=await context(request,write=write)
    if request.query_params:raise AppError('REQUEST_INVALID',422)
    s=request.app.state.settings
    digest=None if write else window_digest(s.login_hmac_secret.get_secret_value(),'http_read','principal',str(ctx.user_id)+':'+str(ctx.tenant_id))
    data=await BuilderRepository(request.app.state.pool).call(ctx,action,asset,version,body,
        UUID(request.state.request_id) if write else None,digest)
    return ctx,data


@router.post('/assets')
async def create(request:Request,body:SaveProfile):
    _,data=await execute(request,'create',body=body.model_dump(mode='json'),write=True)
    return response(request,data,status_code=200 if data['replayed'] else 201)


@router.post('/assets/{asset_id}/versions')
async def append(request:Request,asset_id:UUID,body:AppendProfile):
    _,data=await execute(request,'append',asset_id,body=body.model_dump(mode='json'),write=True)
    return response(request,data,status_code=200 if data['replayed'] else 201)


@router.get('/assets/{asset_id}/versions/{version_id}')
async def version(request:Request,asset_id:UUID,version_id:UUID):
    _,data=await execute(request,'version',asset_id,version_id)
    return response(request,data)


@router.post('/assets/{asset_id}/clone')
async def clone(request:Request,asset_id:UUID,body:CloneProfile):
    _,data=await execute(request,'clone',asset_id,body=body.model_dump(mode='json'),write=True)
    return response(request,data,status_code=200 if data['replayed'] else 201)


@router.post('/assets/{asset_id}/versions/{version_id}/preview')
async def preview(request:Request,asset_id:UUID,version_id:UUID,body:ProfilePreview):
    # POST previews retain CSRF and read-window limits; they never save/run a model.
    ctx=await context(request,write=True)
    _,data=await execute(request,'version',asset_id,version_id)
    names,messages=compose(data['profile'],body.values)
    sources=()
    if data['profile']['document_refs']:
        sources=await SearchRepository(request.app.state.documents).allowed(ctx,data['profile']['document_refs'],request.app.state.settings.mode)
    sealed={'asset_id':str(asset_id),'version_id':str(version_id),'revision':data['revision'],
            'config_hash':data['config_hash'],'profile_hash':data['profile_hash'],'messages':messages,'sources':list(sources),'model_ref':data['profile']['model_ref']}
    hashed=hashlib.sha256(json.dumps(sealed,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return response(request,{**sealed,'composition_hash':hashed,'variables':names,'kind':'composition_preview','provider_called':False})
