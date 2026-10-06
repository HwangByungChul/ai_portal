from datetime import date
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Request
from pydantic import BaseModel,ConfigDict,StrictStr,Field,field_validator
from app.conversations.routes import MetadataRevision,digest
from app.operations.routes import validate_query
from app.tenants.routes import context
from app.errors import AppError,response
from app.feedback.repository import FeedbackRepository

router=APIRouter(prefix='/api/v1')


class FeedbackRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    rating:Literal['positive','negative']
    comment:StrictStr=Field(default='',max_length=1000)
    expected_revision:MetadataRevision

    @field_validator('comment')
    @classmethod
    def comment_valid(cls,value):
        try:value.encode('utf-8')
        except UnicodeError:raise ValueError('COMMENT_INVALID') from None
        if '\x00' in value:raise ValueError('COMMENT_INVALID')
        return value.strip(' ')


class WithdrawRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision:MetadataRevision


@router.get('/runs/{run_id}/feedback')
async def feedback(request:Request,run_id:UUID):
    ctx=await context(request);validate_query(request,set())
    data=await FeedbackRepository(request.app.state.pool).read(ctx,run_id,digest(request,ctx,'http_read'))
    return response(request,data)


@router.put('/runs/{run_id}/feedback')
async def save(request:Request,run_id:UUID,body:FeedbackRequest):
    ctx=await context(request,write=True);validate_query(request,set())
    data=await FeedbackRepository(request.app.state.pool).mutate(ctx,run_id,body.model_dump(exclude={'expected_revision'}),body.expected_revision,False,UUID(request.state.request_id))
    return response(request,data)


@router.delete('/runs/{run_id}/feedback')
async def withdraw(request:Request,run_id:UUID,body:WithdrawRequest):
    ctx=await context(request,write=True);validate_query(request,set())
    data=await FeedbackRepository(request.app.state.pool).mutate(ctx,run_id,{},body.expected_revision,True,UUID(request.state.request_id))
    return response(request,data)


@router.get('/admin/feedback/summary')
async def summary(request:Request,period:date|None=None,agent_key:Literal['general','rules_rag']|None=None):
    ctx=await context(request);validate_query(request,{'period','agent_key'})
    period=period or request.app.state.settings.budget_period
    if period.day!=1 or not 2000<=period.year<=2100:raise AppError('REQUEST_INVALID',422)
    data=await FeedbackRepository(request.app.state.pool).summary(ctx,period,request.app.state.settings.mode,agent_key,digest(request,ctx,'operations_read'))
    return response(request,data)
