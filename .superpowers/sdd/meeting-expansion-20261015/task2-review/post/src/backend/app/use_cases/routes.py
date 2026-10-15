"""Standard Business Use Case Agents Router."""
from uuid import UUID
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator, model_validator

from app.errors import AppError, response
from app.use_cases.meeting import MeetingInput, DocumentRef
from datetime import date
from app.use_cases.runtime import QualityReview
from app.tenants.routes import context
from app.guardrails.engine import evaluate_input
from app.use_cases.catalog import get_use_cases, get_use_case

router = APIRouter(prefix="/api/v1/use-cases")


class ExecuteUseCaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: StrictStr = Field(default="", max_length=4000)

    meeting_date: date | None = None
    document_refs: list[DocumentRef] = Field(default_factory=list, max_length=3)

    @field_validator('meeting_date', mode='before')
    @classmethod
    def strict_date(cls,value):return MeetingInput.valid_date(value)

    @model_validator(mode='after')
    def valid_source(self):
        MeetingInput(memo=self.prompt,meeting_date=self.meeting_date,document_refs=self.document_refs)
        return self
    client_request_id: UUID


@router.get("")
async def list_use_cases(request: Request):
    """Return catalog of all 10 standard business agents."""
    ctx = await context(request)
    service=getattr(request.app.state,'use_case_execution',None)
    agents=[]
    for manifest in get_use_cases():
        binding=await service.ready(ctx,manifest.use_case_id) if service and request.app.state.settings.execution_enabled else None
        agents.append(manifest.to_dict() | {'execution_ready':binding is not None,'approved_version_id':binding['version_id'] if binding else None})
    return response(request, {"items": agents, "total_count": len(agents)})


@router.get("/{use_case_id}")
async def get_use_case_detail(request: Request, use_case_id: str):
    """Return detailed specification for a given business agent."""
    ctx = await context(request)
    manifest = get_use_case(use_case_id)
    if not manifest:
        raise AppError("NOT_FOUND", 404)
    service=getattr(request.app.state,'use_case_execution',None)
    binding=await service.ready(ctx,use_case_id) if service and request.app.state.settings.execution_enabled else None
    return response(request, manifest.to_dict() | {'execution_ready':binding is not None,'approved_version_id':binding['version_id'] if binding else None})


@router.post("/{use_case_id}/execute")
async def execute_use_case(request: Request, use_case_id: str, body: ExecuteUseCaseRequest):
    """Execute a business agent with guardrail validation, tool orchestration, and safety gates."""
    ctx = await context(request, write=True)
    if not getattr(request.app.state.settings, 'execution_enabled', False):
        raise AppError("EXECUTION_NOT_READY", 409)

    manifest = get_use_case(use_case_id)
    if not manifest:
        raise AppError("NOT_FOUND", 404)

    prompt = body.prompt
    if use_case_id != "AGENT_03" and body.model_fields_set & {"meeting_date","document_refs"}:
        raise AppError("REQUEST_INVALID", 422)
    try:source=MeetingInput(memo=prompt,meeting_date=body.meeting_date,document_refs=body.document_refs)
    except ValueError:raise AppError("REQUEST_INVALID",422) from None

    # 1. Input Guardrail Inspection
    g_res = evaluate_input(prompt)
    if use_case_id!='AGENT_03' and g_res.action == "block":
        raise AppError("GUARDRAIL_INPUT_BLOCKED", 422)

    executor=getattr(request.app.state,'use_case_execution',None)
    if executor is None:raise AppError('EXECUTION_NOT_READY',409)
    data=await executor.submit(ctx,use_case_id,prompt,body.client_request_id,source.meeting_date,source.document_refs)
    return response(request,data,status_code=200 if data['replayed'] else 202)


class CancelUseCaseRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision:StrictInt=Field(ge=1,le=9223372036854775806)

def service(request):
    value=getattr(request.app.state,'use_case_execution',None)
    if value is None:raise AppError('EXECUTION_NOT_READY',409)
    return value

@router.get('/{use_case_id}/runs/{run_id}')
async def read_run(request:Request,use_case_id:str,run_id:UUID):
    ctx=await context(request)
    await request.app.state.documents.read_window(ctx)
    return response(request,await service(request).read(ctx,use_case_id,run_id))

@router.post('/{use_case_id}/runs/{run_id}/cancel')
async def cancel_run(request:Request,use_case_id:str,run_id:UUID,body:CancelUseCaseRequest):
    ctx=await context(request,write=True)
    return response(request,await service(request).cancel(ctx,use_case_id,run_id,body.expected_revision))

@router.get('/AGENT_03/documents')
async def meeting_documents(request:Request,cursor:UUID|None=None,limit:int=Query(default=20,ge=1,le=20)):
    ctx=await context(request)
    params=request.query_params
    if set(params)-{'cursor','limit'} or any(len(params.getlist(k))!=1 for k in params):raise AppError('REQUEST_INVALID',422)
    return response(request,await service(request).meetings.candidates(ctx,cursor,limit))

@router.get('/AGENT_03/runs/{run_id}/quality')
async def meeting_quality(request:Request,run_id:UUID):
    ctx=await context(request)
    if request.query_params:raise AppError('REQUEST_INVALID',422)
    await service(request).own(ctx,'AGENT_03',run_id)
    return response(request,await service(request).meetings.quality(ctx,run_id))

@router.get('/AGENT_03/runs/{run_id}/quality/history')
async def meeting_quality_history(request:Request,run_id:UUID):
    return await meeting_quality(request,run_id)

@router.post('/AGENT_03/runs/{run_id}/quality')
async def review_meeting_quality(request:Request,run_id:UUID,body:QualityReview):
    ctx=await context(request,write=True)
    if request.query_params:raise AppError('REQUEST_INVALID',422)
    await service(request).own(ctx,'AGENT_03',run_id)
    data=await service(request).meetings.quality(ctx,run_id,body)
    return response(request,data,status_code=200 if data['replayed'] else 201)
