"""Bounded ephemeral draft snapshots; never infer completion from delivery EOF."""
import asyncio
from datetime import datetime,timezone
import json
from uuid import UUID
from fastapi import APIRouter,Request
from starlette.responses import StreamingResponse
from app.ai.repository import ExecutionError
from app.errors import AppError
from app.tenants.routes import context
from app.operations.routes import validate_query
from app.conversations.routes import digest
from app.conversations.repository import ConversationRepository

router=APIRouter(prefix='/api/v1')
TERMINAL={'completed','failed','blocked','cancelled','interrupted'}

class StreamHub:
    def __init__(self):self.drafts={};self.subscriptions=set();self.closed=False
    def begin(self,run):self.drafts[(run.tenant_id,run.run_id)]={'epoch':run.epoch,'seq':0,'text':''}
    def append(self,run,text):
        item=self.drafts.get((run.tenant_id,run.run_id))
        if item is None or item['epoch']!=run.epoch:return
        if len((item['text']+text).encode('utf-8'))>65536:raise ExecutionError('OUTPUT_TRUNCATED')
        item['text']+=text;item['seq']+=1
    def clear(self,run):self.drafts.pop((run.tenant_id,run.run_id),None)
    def acquire(self,ctx,run_id):
        key=(ctx.user_id,ctx.tenant_id,run_id)
        if self.closed or any(s[1:]==key[1:] for s in self.subscriptions) or sum(s[0]==ctx.user_id for s in self.subscriptions)>=2:
            raise AppError('STREAM_LIMIT_REACHED',429)
        self.subscriptions.add(key);return key
    def release(self,key):self.subscriptions.discard(key)
    def close(self):self.closed=True;self.drafts.clear();self.subscriptions.clear()

    async def events(self,ctx,run_id,repository,mode,key):
        seq=0;last=None;last_keepalive=asyncio.get_running_loop().time()
        def event(kind,view,data):
            nonlocal seq
            seq+=1
            payload={'tenant_id':str(ctx.tenant_id),'run_id':str(run_id),'execution_epoch':view.get('execution_epoch'),
                'sequence':seq,'timestamp':datetime.now(timezone.utc).isoformat(),'data':data}
            return 'event: '+kind+'\ndata: '+json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n\n'
        try:
            while not self.closed:
                try:view=await repository.stream_view(ctx,run_id,mode)
                except ExecutionError:
                    yield event('delivery_error',{}, {'error_code':'STREAM_ACCESS_UNAVAILABLE'});return
                if last is None:
                    last=(view['revision'],-1)
                    yield event('snapshot',view,view)
                    # Resuming after yield always revalidates before another body event.
                    continue
                if view['state'] in TERMINAL:
                    yield event('terminal',view,view);return
                draft=self.drafts.get((ctx.tenant_id,run_id))
                sent=False
                if draft is not None and draft['epoch']==view['execution_epoch'] and draft['text'] and draft['seq']!=last[1]:
                    last=(view['revision'],draft['seq']);sent=True
                    yield event('draft_delta',view,{'text':draft['text'],'draft_sequence':draft['seq'],'replace':True})
                elif view['revision']!=last[0]:
                    last=(view['revision'],draft['seq'] if draft else 0);sent=True
                    yield event('status',view,view)
                now=asyncio.get_running_loop().time()
                if now-last_keepalive>=15:yield ': keepalive\n\n';last_keepalive=now
                await asyncio.sleep(0.25)
        finally:self.release(key)

@router.get('/runs/{run_id}/events')
async def events(request:Request,run_id:UUID):
    ctx=await context(request);validate_query(request,set())
    if 'text/event-stream' not in request.headers.get('accept',''):raise AppError('REQUEST_INVALID',422)
    manager=getattr(request.app.state,'execution',None)
    # Charge only subscription admission to the shared HTTP read window.
    await ConversationRepository(request.app.state.pool).read(ctx,'run',run_id,None,20,digest(request,ctx,'http_read'))
    if manager is None:raise AppError('FEATURE_NOT_READY',409)
    try:await manager.repository.stream_view(ctx,run_id,manager.mode)
    except ExecutionError:raise AppError('STREAM_ACCESS_UNAVAILABLE',403) from None
    hub=manager.hub;key=hub.acquire(ctx,run_id)
    return StreamingResponse(hub.events(ctx,run_id,manager.repository,manager.mode,key),media_type='text/event-stream',
        headers={'Cache-Control':'no-store','X-Accel-Buffering':'no','X-Request-ID':request.state.request_id})
