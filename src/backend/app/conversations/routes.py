from typing import Literal,Annotated
from uuid import UUID
from fastapi import APIRouter,Request,Query
from pydantic import BaseModel,ConfigDict,Field,StrictStr,StrictBool,StrictInt,model_validator
from app.auth.crypto import window_digest
from app.conversations.pagination import decode_cursor,encode_cursor
from app.conversations.repository import ConversationRepository
from app.errors import AppError,response
from app.operations.routes import Revision,validate_query
from app.tenants.routes import context
from app.guardrails.engine import evaluate_input,text_hash
from app.guardrails.routes import record_violation

router=APIRouter(prefix='/api/v1')


class ConversationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    agent_key:Literal['general','rules_rag']
    client_conversation_id:UUID|None=None


MetadataRevision=Annotated[StrictInt,Field(ge=0,le=9223372036854775807)]


class MetadataRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision:MetadataRevision
    title:StrictStr|None=None
    pinned:StrictBool|None=None

    @model_validator(mode='after')
    def validate_metadata(self):
        fields=self.model_fields_set-{'expected_revision'}
        if not fields:raise ValueError('METADATA_REQUIRED')
        if 'title' in fields:
            if self.title is None:raise ValueError('TITLE_REQUIRED')
            try:self.title.encode('utf-8')
            except UnicodeError:raise ValueError('TITLE_INVALID') from None
            if any(c in self.title for c in ('\x00','\r','\n')):raise ValueError('TITLE_INVALID')
            self.title=self.title.strip(' ')
            if not 1<=len(self.title)<=120:raise ValueError('TITLE_INVALID')
        if 'pinned' in fields and self.pinned is None:raise ValueError('PIN_REQUIRED')
        return self


class DeleteConversationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision:MetadataRevision


class DocumentRef(BaseModel):
    model_config=ConfigDict(extra='forbid')
    document_id:UUID
    version_id:UUID


class RunRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    client_send_id:UUID
    conversation_id:UUID|None=None
    agent_key:Literal['general','rules_rag']
    asset_id:UUID|None=None
    prompt:StrictStr=Field(max_length=4000)
    document_refs:list[DocumentRef]|None=Field(default=None,max_length=5)

    @model_validator(mode='after')
    def validate_prompt(self):
        if not self.prompt.strip():raise ValueError('PROMPT_REJECTED')
        try:size=len(self.prompt.encode('utf-8'))
        except UnicodeError:raise ValueError('PROMPT_REJECTED') from None
        if size>16384 or '\x00' in self.prompt:raise ValueError('PROMPT_REJECTED')
        return self


class CancelRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision:Revision


def digest(request,ctx,purpose):
    settings=request.app.state.settings
    return window_digest(settings.login_hmac_secret.get_secret_value(),purpose,'principal',str(ctx.user_id)+':'+str(ctx.tenant_id))


async def read(request,kind,target=None,cursor=None,limit=20,query="",pinned=None):
    ctx=await context(request);validate_query(request,{'cursor','limit','q','pinned'} if kind=='conversations' else {'cursor','limit'} if kind=='messages' else set())
    secret=request.app.state.settings.login_hmac_secret.get_secret_value()
    position=decode_cursor(secret,ctx,kind,target,cursor,query,pinned)
    data=await ConversationRepository(request.app.state.pool).read(ctx,kind,target,position,limit,digest(request,ctx,'http_read'),query,pinned)
    if kind in ('conversations','messages'):
        rows=data['items'];more=len(rows)>limit;rows=rows[:limit]
        data={'items':rows,'next_cursor':encode_cursor(secret,ctx,kind,target,rows[-1],query,pinned) if more else None}
    return response(request,data)


@router.post('/conversations')
async def create_conversation(request:Request,body:ConversationRequest):
    ctx=await context(request,write=True);validate_query(request,set())
    data=await ConversationRepository(request.app.state.pool).create(ctx,body.agent_key,body.client_conversation_id,UUID(request.state.request_id))
    return response(request,data,status_code=200 if data['replayed'] else 201)

@router.get('/conversations')
async def conversations(request:Request,cursor:str|None=None,limit:int=Query(default=20,ge=1,le=50),q:str=Query(default='',max_length=120),pinned:bool|None=None):
    try:q.encode('utf-8')
    except UnicodeError:raise AppError('REQUEST_INVALID',422) from None
    if any(c in q for c in ('\x00','\r','\n')):raise AppError('REQUEST_INVALID',422)
    return await read(request,'conversations',cursor=cursor,limit=limit,query=q.strip(),pinned=pinned)

@router.patch('/conversations/{conversation_id}')
async def metadata(request:Request,conversation_id:UUID,body:MetadataRequest):
    ctx=await context(request,write=True);validate_query(request,set())
    data=await ConversationRepository(request.app.state.pool).mutate(ctx,conversation_id,body.model_dump(exclude_unset=True,exclude={'expected_revision'}),body.expected_revision,False,UUID(request.state.request_id))
    return response(request,data)

@router.delete('/conversations/{conversation_id}')
async def delete_conversation(request:Request,conversation_id:UUID,body:DeleteConversationRequest):
    ctx=await context(request,write=True);validate_query(request,set())
    data=await ConversationRepository(request.app.state.pool).mutate(ctx,conversation_id,{},body.expected_revision,True,UUID(request.state.request_id))
    return response(request,data)

@router.get('/conversations/{conversation_id}/messages')
async def messages(request:Request,conversation_id:UUID,cursor:str|None=None,limit:int=Query(default=20,ge=1,le=50)):
    return await read(request,'messages',conversation_id,cursor,limit)

@router.post('/runs')
async def runs(request:Request,body:RunRequest):
    ctx=await context(request,write=True);validate_query(request,set())
    if body.agent_key=='general' and 'document_refs' in body.model_fields_set:raise AppError('REQUEST_INVALID',422)
    g_res=await request.app.state.guardrails.inspect(ctx,body.prompt,direction='input',trace_id=UUID(request.state.request_id))
    if g_res.action=='block':
        raise AppError('GUARDRAIL_INPUT_BLOCKED',422)
    settings=request.app.state.settings
    manager=getattr(request.app.state,'execution',None)
    if manager is not None and (manager.closed or manager.gateway.stop_latch):raise AppError('PROJECT_STOPPED',503)
    data=await ConversationRepository(request.app.state.pool).admit(ctx,body.agent_key,body.conversation_id,body.client_send_id,
        body.prompt,settings.budget_period,settings.mode,digest(request,ctx,'run_admission'),UUID(request.state.request_id),refs=[x.model_dump() for x in body.document_refs] if body.document_refs else None,documents=request.app.state.documents,asset_id=body.asset_id)
    manager=getattr(request.app.state,'execution',None)
    if manager is not None and not data['replayed'] and not data['is_terminal']:manager.notify(ctx,data['run_id'])
    return response(request,data,status_code=200 if data['is_terminal'] else 202)

@router.get('/runs/by-send/{client_send_id}')
async def by_send(request:Request,client_send_id:UUID):return await read(request,'by_send',client_send_id)

@router.get('/runs/{run_id}')
async def run(request:Request,run_id:UUID):return await read(request,'run',run_id)

@router.post('/runs/{run_id}/cancel')
async def cancel(request:Request,run_id:UUID,body:CancelRequest):
    ctx=await context(request,write=True);validate_query(request,set())
    data=await ConversationRepository(request.app.state.pool).cancel(ctx,run_id,body.expected_revision,UUID(request.state.request_id))
    manager=getattr(request.app.state,'execution',None)
    if manager is not None:manager.cancel(ctx,run_id)
    return response(request,data,status_code=200 if data['is_terminal'] else 202)
