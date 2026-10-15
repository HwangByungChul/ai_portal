"""Standard Business Use Case Agents Router."""
from typing import Any
from uuid import UUID,uuid4
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from app.errors import AppError, response
from app.tenants.routes import context
from app.guardrails.engine import evaluate_input, evaluate_output
from app.tools.registry import GLOBAL_TOOL_REGISTRY
from app.use_cases.catalog import get_use_cases, get_use_case, UseCaseManifest

router = APIRouter(prefix="/api/v1/use-cases")


class ExecuteUseCaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: StrictStr = Field(..., min_length=1, max_length=4000)
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

    prompt = body.prompt.strip()
    if not prompt:
        raise AppError("REQUEST_INVALID", 422)

    # 1. Input Guardrail Inspection
    g_res = evaluate_input(prompt)
    if use_case_id!='AGENT_03' and g_res.action == "block":
        raise AppError("GUARDRAIL_INPUT_BLOCKED", 422)

    executor=getattr(request.app.state,'use_case_execution',None)
    if executor is None:raise AppError('EXECUTION_NOT_READY',409)
    data=await executor.submit(ctx,use_case_id,prompt,body.client_request_id)
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
