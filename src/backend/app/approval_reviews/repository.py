"""Scoped signed keyset pages and exact request reads; SQL retains authorization."""
import base64,hashlib,hmac,json
from uuid import uuid4
from psycopg.types.json import Jsonb
from app.errors import AppError
from app.workflows.identity import runtime_digest
from app.use_cases.meeting import meeting_contract

def cursor_encode(secret,data):
    raw=json.dumps(data,sort_keys=True,separators=(',',':')).encode()
    return base64.urlsafe_b64encode(raw+hmac.new(secret.encode(),raw,hashlib.sha256).digest()).decode().rstrip('=')
def cursor_decode(secret,value,scope):
    try:
        if len(value)>2048:raise ValueError()
        raw=base64.urlsafe_b64decode(value+'='*(-len(value)%4));body,sig=raw[:-32],raw[-32:]
        if not hmac.compare_digest(sig,hmac.new(secret.encode(),body,hashlib.sha256).digest()):raise ValueError()
        data=json.loads(body)
        if any(data.get(k)!=v for k,v in scope.items()):raise ValueError()
        return {'after_time':data['after_time'],'after_id':data['after_id']}
    except (ValueError,KeyError,TypeError,UnicodeError):raise AppError('REQUEST_INVALID',422) from None

class ReviewRepository:
    def __init__(self,repository,kind,mode='mock',secret=''):
        self.repository=repository;self.kind=kind;self.mode=mode;self.secret=secret
    async def read(self,ctx,target=None,body=None):
        contract=meeting_contract()
        payload=(body or {})|{'runtime_digest':runtime_digest(),'meeting_digest':contract['manifest_digest']}
        args=(ctx.session_id,ctx.tenant_id,self.kind,target,Jsonb(payload),self.mode)
        call=self.repository.call if self.kind=='workflow' else self.repository._rpc
        return await call(ctx,'approval_review_read',args)
    async def page(self,ctx,status=None,q='',cursor=None,limit=20):
        scope={'tenant':str(ctx.tenant_id),'actor':str(ctx.user_id),'kind':self.kind,'status':status,'q':q}
        after=cursor_decode(self.secret,cursor,scope) if cursor else {}
        data=await self.read(ctx,body={'status':status,'q':q,'limit':limit+1}|after)
        more=len(data['items'])>limit;data['items']=data['items'][:limit]
        last=data['items'][-1] if data['items'] else None
        data['next_cursor']=cursor_encode(self.secret,scope|{'after_time':last['created_at'],'after_id':last['request_id' if self.kind=='tool' else 'version_id']}) if more else None
        return data
    async def detail(self,ctx,target):
        data=await self.read(ctx,target)
        current=data['current_head'];request=data['request']
        fields=['descriptor','audience','member_ids'] if self.kind=='tool' else ['definition','audience','member_ids','execution_mode','runtime_digest','use_case_id','use_case_digest','manifest_snapshot']
        data['diff']={'baseline_available':current is not None,'changes':[{'field':key,'before':current.get(key) if current else None,'after':request.get(key)} for key in fields if current is None or current.get(key)!=request.get(key)]}
        if self.kind=='workflow':
            from app.workflows.approved_models import ApprovedWorkflow
            try:ApprovedWorkflow.model_validate(request['definition'])
            except ValueError:
                data['validation']['valid']=False;data['can_approve']=False
                data['validation']['checks'].append({'code':'SCHEMA_INVALID','status':'fail','message':'현재 승인 Workflow 스키마와 일치하지 않습니다.'})
        return data

def query_page(request):
    allowed={'status','q','cursor','limit'}
    if set(request.query_params)-allowed or any(len(request.query_params.getlist(k))!=1 for k in request.query_params):raise AppError('REQUEST_INVALID',422)
    status=request.query_params.get('status');q=request.query_params.get('q','').strip();cursor=request.query_params.get('cursor')
    try:limit=int(request.query_params.get('limit','20'))
    except ValueError:raise AppError('REQUEST_INVALID',422) from None
    if status not in (None,'pending','approved','rejected') or not 1<=limit<=50 or len(q)>120 or '\x00' in q:raise AppError('REQUEST_INVALID',422)
    try:q.encode('utf-8')
    except UnicodeError:raise AppError('REQUEST_INVALID',422) from None
    return {'status':status,'q':q,'cursor':cursor,'limit':limit}

def secret(request):
    value=request.app.state.settings.login_hmac_secret
    return value.get_secret_value() if value else ''
