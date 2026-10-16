"""Fixed Workflow capabilities; definitions and private checkpoint content stay server-owned."""
import hashlib
import json
from datetime import date
from uuid import UUID,uuid4
import psycopg
from psycopg.types.json import Jsonb
from app.db import tenant_transaction
from app.errors import AppError
from app.workflows.identity import runtime_digest


class WorkflowRepository:
    def __init__(self,pool,period=date(2026,10,1),mode='mock'):
        self.pool=pool;self.period=period;self.mode=mode

    @staticmethod
    def digest(definition):
        data=json.dumps(definition,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        if len(data)>24576:raise AppError('REQUEST_INVALID',422)
        return hashlib.sha256(data).hexdigest()

    async def call(self,ctx,name,args):
        try:
            async with tenant_transaction(self.pool,ctx) as conn:
                data=await (await conn.execute('SELECT security.'+name+'('+','.join(['%s']*len(args))+') AS data',args)).fetchone()
                return data['data']
        except (psycopg.Error,ValueError) as error:
            codes={'A0401':('AUTH_REQUIRED',401),'A0403':('MANAGEMENT_DENIED',403),'A0404':('NOT_FOUND',404),'A0409':('REVISION_CONFLICT',409),'A0422':('REQUEST_INVALID',422),'22P02':('REQUEST_INVALID',422),'A0429':('WORKFLOW_QUEUE_LIMIT',429),'B0401':('WORKFLOW_BLOCKED',409),'D0404':('DOCUMENT_UNAVAILABLE',404),'B0340':('WORKFLOW_BLOCKED',409)}
            if isinstance(error,ValueError):raise AppError('AUTH_REQUIRED',401) from None
            raise AppError(*codes.get(error.sqlstate,('STORAGE_UNAVAILABLE',503))) from None

    async def approval(self,ctx,action,target,body,mode,trace=None):
        from app.use_cases.meeting import meeting_contract
        contract=meeting_contract()
        sealed=body|{'meeting_digest':contract['manifest_digest'],'runtime_digest':runtime_digest(),'execution_mode':mode,'budget_period':self.period.isoformat()}
        if action=='submit' and body.get('use_case_id')=='AGENT_03':sealed['manifest_snapshot']=contract
        return await self.call(ctx,'workflow_approval_control',(ctx.session_id,ctx.tenant_id,action,target,Jsonb(sealed),mode,trace or uuid4()))

    async def runtime(self,ctx,action,target=None,body=None,token=None,trace=None):
        return await self.call(ctx,'workflow_runtime',(ctx.session_id,ctx.tenant_id,action,target,Jsonb(body or {}),self.mode,runtime_digest(),token,self.period,trace or uuid4()))

    async def child(self,ctx,parent,node,token,config,values,window,guardrails=None):
        from app.assets.published import PublishedRepository
        from app.builder.schemas import compose
        from app.ai.token_limits import general_token_count,count_embedding_tokens
        pub=await PublishedRepository(self.pool).asset(ctx,UUID(config['asset_id']),self.mode)
        if pub['version_id']!=config['version_id'] or pub['publication_revision']!=config['publication_revision']:raise AppError('REVISION_CONFLICT',409)
        _,messages=compose(pub['profile'],values);tokens=general_token_count(messages)
        if guardrails is not None:
            checked=await guardrails.inspect(ctx,'\n'.join(m['content'] for m in messages),direction='input')
            if checked.action=='block':raise AppError('GUARDRAIL_INPUT_BLOCKED',422)
        if tokens>6000 or len(messages[-1]['content'])>4000 or pub['config']['execution_kind']=='rules_rag' and count_embedding_tokens(messages[-1]['content'])>4000:raise AppError('TOKEN_LIMIT_EXCEEDED',422)
        data=await self.call(ctx,'workflow_child_admit',(ctx.session_id,ctx.tenant_id,parent,node,token,Jsonb(values),tokens,window,self.mode,runtime_digest(),self.period,uuid4()))
        if 'admission_error' in data:raise AppError(data['admission_error'],429,data['retry_after'])
        return data

    @staticmethod
    def json(value):return Jsonb(value)

    async def meeting_context(self,ctx,parent):
        return await self.call(ctx,'meeting_context_read',(ctx.session_id,ctx.tenant_id,parent,self.mode))

    async def meeting(self,ctx,parent=None):
        return await self.call(ctx,'meeting_binding',(ctx.session_id,ctx.tenant_id,parent,self.mode,runtime_digest(),self.period))

    async def recover(self):
        try:
            async with self.pool.connection() as conn:
                async with conn.transaction():
                    return (await (await conn.execute('SELECT security.workflow_recover(%s) AS data',(self.mode,))).fetchone())['data']
        except psycopg.Error:raise AppError('STORAGE_UNAVAILABLE',503) from None

    async def recovery(self,ctx,action,target=None,body=None,trace=None):
        return await self.call(ctx,'workflow_recovery_control',(ctx.session_id,ctx.tenant_id,action,target,Jsonb(body or {}),self.mode,runtime_digest(),self.period,trace or uuid4()))

    async def checkpoints(self,ctx,parent):
        return await self.call(ctx,'workflow_checkpoint_load',(ctx.session_id,ctx.tenant_id,parent))


class WorkflowToolRepository:
    """Injects parent capability into every existing Tool admission/dispatch/finish/read."""
    def __init__(self,repository,parent,node,worker):
        self.repository=repository;self.parent=parent;self.node=node;self.worker=worker

    async def execution(self,ctx,action,tool_id,digest,mode,client_id=None,args=None,token=None,result=None,error=''):
        return await self.repository.call(ctx,'workflow_tool_control',(ctx.session_id,ctx.tenant_id,self.parent,self.node,self.worker,action,tool_id,digest,mode,client_id,Jsonb(args or {}),token,Jsonb(result if result is not None else {}),error,self.repository.period,uuid4()))
