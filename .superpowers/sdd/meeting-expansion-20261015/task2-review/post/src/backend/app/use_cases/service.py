"""One approved business case; parent admission, calls and cancellation remain centralized."""
from uuid import UUID
from app.errors import AppError
from app.documents.storage import SourceStorageError
from app.use_cases.meeting import MeetingInput,meeting_contract

class UseCaseExecutionService:
    def __init__(self,workflow,documents=None):
        from app.use_cases.runtime import MeetingRuntime
        self.workflow=workflow;self.repository=workflow.repository
        self.meetings=MeetingRuntime(self.repository,documents)
        self.workflow.meetings=self.meetings
        if workflow.agent_execution is not None:
            workflow.agent_execution.repository.meeting_guard=self.meetings.guard_child

    async def ready(self,ctx,case):
        if case!='AGENT_03' or self.workflow.agent_execution is None:return None
        try:binding=await self.repository.meeting(ctx)
        except AppError as error:
            if error.status in (403,404,409):return None
            raise
        if binding and binding['use_case_digest']==meeting_contract()['manifest_digest']:return binding
        return None

    async def submit(self,ctx,case,prompt,client,meeting_date=None,document_refs=None):
        if case!='AGENT_03':raise AppError('EXECUTION_NOT_READY',409)
        try:source=MeetingInput(memo=prompt,meeting_date=meeting_date,document_refs=document_refs or [])
        except ValueError:raise AppError('REQUEST_INVALID',422) from None
        from app.workflows.identity import runtime_digest
        replay=await self.repository.call(ctx,'meeting_receipt_lookup',(ctx.session_id,ctx.tenant_id,client,self.repository.json(source.model_dump(mode='json')),self.repository.mode,runtime_digest(),self.repository.period))
        if replay is not None:return await self.workflow.safe_public(ctx,replay)
        binding=await self.ready(ctx,case)
        if binding is None:raise AppError('EXECUTION_NOT_READY',409)
        try:sealed=await self.meetings.resolve(ctx,source)
        except SourceStorageError:raise AppError('DOCUMENT_UNAVAILABLE',404) from None
        return await self.workflow.admit(ctx,UUID(binding['version_id']),client,{binding['input_key']:sealed['compiled']},meeting_context=sealed)

    async def own(self,ctx,case,parent):
        binding=await self.repository.meeting(ctx,parent)
        if binding is None or binding['use_case_id']!=case:raise AppError('NOT_FOUND',404)

    async def read(self,ctx,case,parent):
        await self.own(ctx,case,parent)
        return await self.workflow.read(ctx,parent)

    async def cancel(self,ctx,case,parent,revision):
        await self.own(ctx,case,parent)
        return await self.workflow.cancel(ctx,parent,revision)
