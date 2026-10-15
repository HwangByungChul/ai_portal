"""Durable standalone read Tool execution; a dispatched request is never redispatched."""
import asyncio
import hashlib
import json
from uuid import UUID,uuid4
from pathlib import Path
from app.errors import AppError
from app.tools.adapters import FixtureToolAdapter

class ToolExecutionService:
    def __init__(self,repository,registry,mode,guardrails):
        if mode not in ('mock','real'):raise ValueError('MODE_INVALID')
        self.repository=repository;self.registry=registry;self.mode=mode;self.guardrails=guardrails

    def descriptor(self,tool_id):
        tool=self.registry.get(tool_id)
        if tool is None:raise AppError('TOOL_NOT_FOUND',404)
        body={'tool_id':tool_id,'mode':self.mode,'adapter_revision':'fixture-read-v1' if self.mode=='mock' else 'institution-read-unconfigured-v1',
              'registry_module_sha256':hashlib.sha256(Path(__file__).with_name('registry.py').read_bytes()).hexdigest(),'adapter_module_sha256':hashlib.sha256(Path(__file__).with_name('adapters.py').read_bytes()).hexdigest(),'arg_schema':tool.arg_schema,'timeout_seconds':tool.timeout_seconds,'read_only':True}
        body['digest']=hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        return body

    def _configured(self):
        # Real connectors are not yet implemented. Never silently use fixture data.
        if self.mode!='mock' or not isinstance(self.registry._adapter,FixtureToolAdapter):raise AppError('EXECUTION_NOT_READY',409)

    async def ready(self,ctx):
        items=[]
        for tool in self.registry.list_public():
            descriptor=self.descriptor(tool['tool_id'])
            ready=False
            if self.mode=='mock':
                ready=(await self.repository.execution(ctx,'ready',tool['tool_id'],descriptor['digest'],self.mode))['execution_ready']
            items.append(tool|{'execution_ready':ready,'execution_mode':self.mode,'version_digest':descriptor['digest']})
        return items

    @staticmethod
    def public(receipt):return {k:v for k,v in receipt.items() if k!='claimed'}

    async def replay(self,ctx,receipt):
        data=self.public(receipt)
        if receipt['state']=='succeeded':
            encoded=json.dumps(receipt['result'],ensure_ascii=False,allow_nan=False,separators=(',',':'))
            checked=await self.guardrails.inspect(ctx,encoded,direction='output')
            if checked.action=='block':
                data['result']=None;data['result_access']='blocked'
            elif checked.action=='mask':
                try:data['result']=json.loads(checked.masked_text)
                except (TypeError,ValueError):
                    data['result']=None;data['result_access']='blocked'
        if receipt['state']=='succeeded':
            # Recheck the current permit after asynchronous policy/audit inspection.
            await self.repository.execution(ctx,'read',receipt['tool_id'],receipt['version_digest'],self.mode,UUID(receipt['client_request_id']))
        return data

    async def read(self,ctx,tool_id,client_id):
        self._configured();d=self.descriptor(tool_id)
        result=await self.repository.execution(ctx,'read',tool_id,d['digest'],self.mode,UUID(str(client_id)))
        return await self.replay(ctx,result)

    async def invoke(self,ctx,tool_id,args,client_id):
        self._configured()
        try:cid=UUID(str(client_id))
        except (ValueError,TypeError,AttributeError):raise AppError('REQUEST_INVALID',422) from None
        tool=self.registry.validate(tool_id,args);descriptor=self.descriptor(tool_id)
        encoded=json.dumps(args,ensure_ascii=False,allow_nan=False,separators=(',',':'))
        policy=await self.guardrails.snapshot(ctx)
        checked=await self.guardrails.inspect(ctx,encoded,direction='input')
        if checked.action=='block':raise AppError('TOOL_INPUT_BLOCKED',422)
        receipt=await self.repository.execution(ctx,'admit',tool_id,descriptor['digest'],self.mode,cid,args)
        if receipt['state']!='accepted':return await self.replay(ctx,receipt)
        token=uuid4()
        receipt=await self.repository.execution(ctx,'dispatch',tool_id,descriptor['digest'],self.mode,cid,token=token)
        if not receipt['claimed']:return await self.replay(ctx,receipt)
        # Publication permission is rechecked by finish; raw handler output never escapes.
        try:
            result=await asyncio.wait_for(asyncio.to_thread(tool.handler,args),tool.timeout_seconds)
        except asyncio.CancelledError:
            await asyncio.shield(self.repository.execution(ctx,'finish',tool_id,descriptor['digest'],self.mode,cid,token=token,error='TOOL_RESULT_UNKNOWN'))
            raise
        except Exception:
            result=await self.repository.execution(ctx,'finish',tool_id,descriptor['digest'],self.mode,cid,token=token,error='TOOL_RESULT_UNKNOWN')
            return self.public(result)
        try:
            encoded=json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(',',':'))
            if len(encoded.encode('utf-8'))>32768:raise ValueError('OUTPUT_LIMIT')
        except (ValueError,TypeError,UnicodeError):
            receipt=await self.repository.execution(ctx,'finish',tool_id,descriptor['digest'],self.mode,cid,token=token,error='TOOL_OUTPUT_INVALID')
            return self.public(receipt)
        safe=await self.guardrails.inspect(ctx,encoded,direction='output',previous=policy)
        if safe.action=='block':
            receipt=await self.repository.execution(ctx,'finish',tool_id,descriptor['digest'],self.mode,cid,token=token,error='TOOL_OUTPUT_BLOCKED')
        else:
            try:result=json.loads(safe.masked_text if safe.action=='mask' else encoded)
            except (ValueError,TypeError):
                receipt=await self.repository.execution(ctx,'finish',tool_id,descriptor['digest'],self.mode,cid,token=token,error='TOOL_OUTPUT_INVALID')
                return self.public(receipt)
            receipt=await self.repository.execution(ctx,'finish',tool_id,descriptor['digest'],self.mode,cid,token=token,result=result)
        return self.public(receipt)
