"""One approved business case; parent admission, calls and cancellation remain centralized."""
from uuid import UUID
from app.errors import AppError
from app.use_cases.meeting import MeetingInput,meeting_contract

class UseCaseExecutionService:
    def __init__(self,workflow):self.workflow=workflow;self.repository=workflow.repository

    async def ready(self,ctx,case):
        if case!='AGENT_03' or self.workflow.agent_execution is None:return None
        try:binding=await self.repository.meeting(ctx)
        except AppError as error:
            if error.status in (403,404,409):return None
            raise
        if binding and binding['use_case_digest']==meeting_contract()['manifest_digest']:return binding
        return None

    async def submit(self,ctx,case,prompt,client):
        if case!='AGENT_03':raise AppError('EXECUTION_NOT_READY',409)
        try:MeetingInput(memo=prompt)
        except ValueError:raise AppError('REQUEST_INVALID',422) from None
        binding=await self.ready(ctx,case)
        if binding is None:raise AppError('EXECUTION_NOT_READY',409)
        return await self.workflow.admit(ctx,UUID(binding['version_id']),client,{binding['input_key']:prompt})

    async def own(self,ctx,case,parent):
        binding=await self.repository.meeting(ctx,parent)
        if binding is None or binding['use_case_id']!=case:raise AppError('NOT_FOUND',404)

    async def read(self,ctx,case,parent):
        await self.own(ctx,case,parent)
        return await self.workflow.read(ctx,parent)

    async def cancel(self,ctx,case,parent,revision):
        await self.own(ctx,case,parent)
        return await self.workflow.cancel(ctx,parent,revision)
