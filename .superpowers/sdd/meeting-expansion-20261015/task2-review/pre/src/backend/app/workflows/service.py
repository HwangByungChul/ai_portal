"""Durable, approval-gated orchestration using existing Agent and Tool execution services."""
import asyncio
import hashlib
import json
from uuid import UUID,uuid4
from app.assets.published import PublishedRepository
from app.conversations.repository import ConversationRepository
from app.errors import AppError
from app.tools.execution import ToolExecutionService
from app.workflows.approved_models import ApprovedWorkflow
from app.workflows.bindings import resolve,resolve_mapping,child_request_id
from app.workflows.repository import WorkflowToolRepository
from app.use_cases.meeting import MeetingInput,MeetingResult


class WorkflowExecutionService:
    def __init__(self,repository,agent_execution,tools,guardrails):
        self.repository=repository;self.agent_execution=agent_execution;self.tools=tools;self.guardrails=guardrails
        self.tasks={};self.closed=False;self.leader=None;self.recovery=None

    async def start(self):
        self.leader=await self.repository.pool.getconn()
        try:
            row=await (await self.leader.execute('SELECT pg_try_advisory_lock(202610,5) AS ok')).fetchone()
            if not row['ok']:raise AppError('EXECUTION_NOT_READY',409)
            # Existing ExecutionManager has already recovered its child run/call ledgers.
            async with self.leader.transaction():
                self.recovery=(await (await self.leader.execute('SELECT security.workflow_recover(%s) AS data',(self.repository.mode,))).fetchone())['data']
        except BaseException:
            await self.leader.close();await self.repository.pool.putconn(self.leader);self.leader=None;raise

    async def admit(self,ctx,version,client,inputs,trace=None):
        if self.closed or self.agent_execution is None:raise AppError('EXECUTION_NOT_READY',409)
        detail=await self.repository.runtime(ctx,'definition',UUID(str(version)))
        definition=ApprovedWorkflow.model_validate(detail['definition'])
        key=next(n.config['input_key'] for n in definition.nodes if n.node_type=='input')
        if set(inputs)!={key} or not isinstance(inputs[key],str) or not inputs[key].strip() or len(inputs[key])>4000:raise AppError('REQUEST_INVALID',422)
        try:
            if '\x00' in inputs[key]:raise ValueError('invalid')
            inputs[key].encode('utf-8')
        except (ValueError,UnicodeError):raise AppError('REQUEST_INVALID',422) from None
        for node in definition.nodes:
            if node.node_type=='read_tool':
                self.tools._configured()
                if self.tools.descriptor(node.config['tool_id'])['digest']!=node.config['version_digest']:raise AppError('REVISION_CONFLICT',409)
        checked=await self.guardrails.inspect(ctx,json.dumps(inputs,ensure_ascii=False),direction='input')
        if checked.action=='block':raise AppError('GUARDRAIL_INPUT_BLOCKED',422)
        data=await self.repository.runtime(ctx,'admit',body={'version_id':str(version),'client_request_id':str(client),'inputs':inputs},trace=trace)
        if not data['is_terminal']:self.notify(ctx,data['run_id'])
        return await self.safe_public(ctx,data)

    def notify(self,ctx,run_id):
        key=(ctx.tenant_id,UUID(str(run_id)))
        if self.closed or key in self.tasks:return
        task=asyncio.create_task(self._run(ctx,key[1]));self.tasks[key]=task
        task.add_done_callback(lambda _:self.tasks.pop(key,None))

    async def safe_public(self,ctx,data):
        if data.get('result_access')=='final':
            try:value=await self.safe_value(ctx,data['result'])
            except AppError as error:
                if error.code=='GUARDRAIL_OUTPUT_BLOCKED':return data|{'result':None,'result_access':'blocked'}
                raise
            current=await self.repository.runtime(ctx,'read',UUID(data['run_id']))
            if current.get('result_access')!='final':return data|current
            data=data|current|{'result':value}
        return data

    async def read(self,ctx,parent):
        data=await self.repository.runtime(ctx,'read',parent)
        try:return await self.safe_public(ctx,data)
        except AppError as error:
            if error.code=='GUARDRAIL_OUTPUT_BLOCKED':return data|{'result':None,'result_access':'blocked'}
            raise

    async def safe_value(self,ctx,value,previous=None):
        encoded=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))
        if len(encoded.encode())>32768:raise AppError('PAYLOAD_TOO_LARGE',422)
        checked=await self.guardrails.inspect(ctx,encoded,direction='output',previous=previous)
        if checked.action=='block':raise AppError('GUARDRAIL_OUTPUT_BLOCKED',422)
        if checked.action=='mask':
            if isinstance(value,str):return checked.masked_text
            try:return json.loads(checked.masked_text)
            except (TypeError,ValueError):raise AppError('GUARDRAIL_OUTPUT_BLOCKED',422) from None
        return value

    async def cleanup_children(self,ctx,data):
        for step in data.get('steps',[]):
            child=step.get('child_run_id')
            if not child:continue
            child=UUID(child)
            try:
                pub=PublishedRepository(self.repository.pool)
                from psycopg.types.json import Jsonb
                row=await pub.rpc(ctx,'published_run_history',(ctx.session_id,ctx.tenant_id,'record',child,Jsonb({}),self.repository.mode))
                if not row.get('is_terminal',row.get('state') not in ('accepted','running','cancel_requested')):
                    await ConversationRepository(self.repository.pool).cancel(ctx,child,row['revision'],uuid4())
            except AppError:
                # Parent fence already blocks dispatch/save; current child heartbeat also fails closed.
                pass
            if self.agent_execution is not None:self.agent_execution.cancel(ctx,child)

    async def cancel(self,ctx,parent,revision,trace=None):
        data=await self.repository.runtime(ctx,'cancel',parent,{'expected_revision':revision},trace=trace)
        await self.cleanup_children(ctx,data)
        task=self.tasks.get((ctx.tenant_id,parent))
        if task is not None:task.cancel()
        return data

    async def _run(self,ctx,parent):
        token=uuid4();heartbeat=None;reason=None
        async def beat(driver):
            nonlocal reason
            while True:
                await asyncio.sleep(10)
                try:await self.repository.runtime(ctx,'heartbeat',parent,token=token)
                except AppError:
                    reason='WORKFLOW_BLOCKED';driver.cancel();return
        try:
            work=await self.repository.runtime(ctx,'claim',parent,token=token)
            if work is None:return
            definition=ApprovedWorkflow.model_validate(work['definition']);results={}
            binding=await self.repository.meeting(ctx,parent)
            heartbeat=asyncio.create_task(beat(asyncio.current_task()))
            policy=await self.guardrails.snapshot(ctx)
            nodes={n.node_id:n for n in definition.nodes}
            for node_id in definition.order():
                node=nodes[node_id]
                await self.repository.runtime(ctx,'step',parent,{'node_id':node_id},token)
                if node.node_type=='input':value=work['inputs'][node.config['input_key']]
                elif node.node_type=='read_tool':
                    arguments=resolve_mapping(node.config['arguments'],results)
                    bound=ToolExecutionService(WorkflowToolRepository(self.repository,parent,node_id,token),self.tools.registry,self.repository.mode,self.guardrails)
                    receipt=await bound.invoke(ctx,node.config['tool_id'],arguments,child_request_id(parent,node_id,'tool'))
                    if receipt['state']!='succeeded':raise AppError('GUARDRAIL_OUTPUT_BLOCKED' if receipt.get('error_code')=='TOOL_OUTPUT_BLOCKED' else 'WORKFLOW_CHILD_FAILED',409)
                    value=receipt['result']
                elif node.node_type=='llm':
                    values=resolve_mapping(node.config['values'],results)
                    window=hashlib.sha256((str(ctx.tenant_id)+str(ctx.user_id)+':workflow-child').encode()).digest()
                    child=await self.repository.child(ctx,parent,node_id,token,node.config,values,window,guardrails=self.guardrails)
                    child_id=UUID(child['run_id']);self.agent_execution.notify(ctx,child_id)
                    async with asyncio.timeout(180):
                        while True:
                            record=await PublishedRepository(self.repository.pool).read(ctx,child_id)
                            if record['state']=='completed':
                                if record['content_status']!='final' or record['result'] is None:raise AppError('WORKFLOW_CHILD_FAILED',409)
                                value=record['result'];break
                            if record['is_terminal']:raise AppError(record.get('error_code') if record.get('error_code') in ('GUARDRAIL_OUTPUT_BLOCKED','GUARDRAIL_INPUT_BLOCKED','TOOL_INPUT_BLOCKED') else 'WORKFLOW_CHILD_FAILED',409)
                            await asyncio.sleep(.1)
                else:
                    value=resolve(node.config['source'],results)
                    if node.node_type=='validate' and (value is None or isinstance(value,str) and not value.strip() or isinstance(value,dict) and value.get('answer_kind')=='insufficient_evidence'):raise AppError('WORKFLOW_INSUFFICIENT_EVIDENCE',409)
                if binding and node.node_type=='output':
                    source=MeetingInput(memo=work['inputs'][binding['input_key']])
                    value=(MeetingResult.model_validate_json(value) if isinstance(value,str) else MeetingResult.model_validate(value)).check_evidence(source).model_dump(mode='json')
                value=await self.safe_value(ctx,value,policy)
                await self.repository.runtime(ctx,'checkpoint',parent,{'node_id':node_id,'result':value},token)
                results[node_id]=value
            output=next(n.node_id for n in definition.nodes if n.node_type=='output')
            await self.repository.runtime(ctx,'finish',parent,{'result':results[output]},token)
        except asyncio.CancelledError:
            reason=reason or 'WORKFLOW_INTERRUPTED'
        except AppError as error:
            reason=error.code if error.code in ('WORKFLOW_BINDING_INVALID','WORKFLOW_CHILD_FAILED','WORKFLOW_INSUFFICIENT_EVIDENCE') else 'WORKFLOW_BLOCKED' if error.status in (401,403,404) or error.code in ('WORKFLOW_BLOCKED','GUARDRAIL_OUTPUT_BLOCKED','GUARDRAIL_INPUT_BLOCKED','TOOL_INPUT_BLOCKED') else 'WORKFLOW_FAILED'
        except Exception:
            reason='WORKFLOW_FAILED'
        finally:
            if heartbeat is not None:heartbeat.cancel();await asyncio.gather(heartbeat,return_exceptions=True)
            if reason:
                try:
                    data=await self.repository.runtime(ctx,'fail',parent,{'error_code':reason},token)
                    await self.cleanup_children(ctx,data)
                except AppError:pass

    async def close(self):
        self.closed=True
        for task in list(self.tasks.values()):task.cancel()
        await asyncio.gather(*list(self.tasks.values()),return_exceptions=True)
        if self.leader is not None:
            try:await self.leader.execute('SELECT pg_advisory_unlock(202610,5)')
            finally:await self.repository.pool.putconn(self.leader);self.leader=None
