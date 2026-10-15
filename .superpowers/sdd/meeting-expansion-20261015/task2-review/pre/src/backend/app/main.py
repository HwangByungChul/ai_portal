from contextlib import asynccontextmanager,AsyncExitStack
from uuid import uuid4
import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from app.auth.routes import router as auth_router
from app.auth.service import AuthService
from app.tenants.routes import router as tenants_router
from app.operations.routes import router as operations_router
from app.approvals.routes import router as approvals_router
from app.assets.routes import router as assets_router
from app.builder.routes import router as builder_router
from app.builder.profile_routes import router as builder_profiles_router
from app.catalog.routes import router as catalog_router
from app.conversations.routes import router as conversations_router
from app.feedback.routes import router as feedback_router
from app.config import Settings
from app.db import open_web_pool,open_meter_pool
from app.ai.repository import CallRepository
from app.ai.providers import MockProvider,OpenAIProvider
from app.ai.routing import build_model_router
from app.guardrails.service import GuardrailService
from app.ai.token_limits import validate_general_input
from app.execution.manager import ExecutionManager
from app.builder.trials import router as builder_trial_router
from app.builder.evaluations import router as builder_evaluations_router
from app.ai.routes import models_router
from app.builder.shares import router as builder_shares_router
from app.assets.deployments import router as asset_deployments_router
from app.assets.published import router as published_agents_router
from app.execution.stream import StreamHub,router as stream_router
from app.errors import AppError, response
from app.documents.routes import router as documents_router
from app.documents.user_routes import router as user_documents_router
from app.documents.share_routes import router as share_router
from app.documents.evidence_routes import router as evidence_router
from app.execution.rag import RagExecutor
from app.execution.document_summary import SummaryExecutor
from app.execution.summary_routes import router as summary_router
from app.ai.summary_provider import SummaryMockProvider,SummaryOpenAIProvider
from app.ai.rag_provider import RagMockProvider,RagOpenAIProvider
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage
from app.documents.embedding import EmbeddingGateway,MockEmbeddingProvider,OpenAIEmbeddingProvider
from app.documents.worker import DocumentWorker
from app.documents.manager import DocumentManager
from app.documents.data_imports import router as data_imports_router
from app.tools.routes import router as tools_router
from app.tools.repository import ToolRepository
from app.tools.execution import ToolExecutionService
from app.tools.registry import ToolRegistry
from app.tools.adapters import FixtureToolAdapter,RealInstitutionalToolAdapter
from app.workflows.routes import router as workflows_router,admin as workflow_approvals_router
from app.workflows.repository import WorkflowRepository
from app.workflows.service import WorkflowExecutionService
from app.guardrails.routes import router as guardrails_router
from app.use_cases.routes import router as use_cases_router
from app.use_cases.service import UseCaseExecutionService
from app.operations.overview import router as overview_router
from app.db import open_index_pool


def create_app(settings: Settings | None = None, *, health_only: bool = False) -> FastAPI:
    settings = settings or Settings.from_environment()
    if not health_only:
        settings.require_auth_configuration()
        if settings.execution_enabled:settings.require_execution_configuration()
        if settings.index_enabled:settings.require_index_configuration()

    @asynccontextmanager
    async def lifespan(app):
        async with AsyncExitStack() as stack:
            app.state.pool=None;app.state.execution=None;app.state.document_manager=None
            app.state.tool_control=None;app.state.tool_execution=None;app.state.workflow_repository=None;app.state.workflow_control=None;app.state.workflow_execution=None;app.state.use_case_execution=None
            if settings.web_dsn is not None:
                pool=await stack.enter_async_context(open_web_pool(settings.web_dsn.get_secret_value()));app.state.pool=pool
                if not health_only:
                    app.state.auth=AuthService(pool,settings)
                    app.state.guardrails=GuardrailService(pool)
                    tool_registry=ToolRegistry(adapter=FixtureToolAdapter() if settings.mode=='mock' else RealInstitutionalToolAdapter())
                    app.state.tool_control=ToolExecutionService(ToolRepository(pool,settings.budget_period),tool_registry,settings.mode,app.state.guardrails)
                    app.state.workflow_repository=WorkflowRepository(pool,settings.budget_period,settings.mode)
                    if settings.execution_enabled:app.state.tool_execution=app.state.tool_control
                    app.state.documents=DocumentRepository(pool,SourceStorage(settings.source_root),settings.login_hmac_secret.get_secret_value(),settings.mode)
                    if settings.execution_enabled or settings.index_enabled:
                        meter=await stack.enter_async_context(open_meter_pool(settings.meter_dsn.get_secret_value()))
                    if settings.execution_enabled:
                        validate_general_input('질문에 답해 주세요.',[],'준비 확인')
                        provider=OpenAIProvider(settings.openai_api_key.get_secret_value()) if settings.mode=='real' else MockProvider()
                        repository=CallRepository(pool,meter,settings.budget_period)
                        rag=RagExecutor(repository,app.state.documents,OpenAIEmbeddingProvider(settings.openai_api_key.get_secret_value()) if settings.mode=='real' else MockEmbeddingProvider(),RagOpenAIProvider(settings.openai_api_key.get_secret_value()) if settings.mode=='real' else RagMockProvider())
                        summary=SummaryExecutor(repository,app.state.documents,SummaryOpenAIProvider(settings.openai_api_key.get_secret_value()) if settings.mode=='real' else SummaryMockProvider())
                        manager=ExecutionManager(repository,provider,settings.mode,StreamHub(),rag=rag,summary=summary,router=build_model_router(settings),guardrails=app.state.guardrails)
                        await manager.start();stack.push_async_callback(manager.close);app.state.execution=manager
                    workflow=WorkflowExecutionService(app.state.workflow_repository,app.state.execution,app.state.tool_control,app.state.guardrails)
                    app.state.workflow_control=workflow
                    app.state.use_case_execution=UseCaseExecutionService(workflow)
                    if settings.execution_enabled:
                        await workflow.start();stack.push_async_callback(workflow.close);app.state.workflow_execution=workflow
                    if settings.index_enabled:
                        index=await stack.enter_async_context(open_index_pool(settings.index_dsn.get_secret_value()))
                        provider=OpenAIEmbeddingProvider(settings.openai_api_key.get_secret_value()) if settings.mode=='real' else MockEmbeddingProvider()
                        worker=DocumentWorker(app.state.documents,EmbeddingGateway(index,meter,provider,settings.budget_period));manager=DocumentManager(worker,settings.mode)
                        await manager.start();stack.push_async_callback(manager.close);app.state.document_manager=manager
            yield

    app = FastAPI(title='AI Platform MVP', version='0.1.0', lifespan=lifespan)
    app.state.settings = settings

    @app.middleware('http')
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        if (request.method=='PUT' and (request.url.path.startswith('/api/v1/catalog/assets/') or request.url.path.startswith('/api/v1/admin/agent-access/') or request.url.path.startswith('/api/v1/published-agents/'))) or request.method=='POST' and (request.url.path in ('/api/v1/runs','/api/v1/conversations') or request.url.path.startswith('/api/v1/document-summaries') or request.url.path.startswith('/api/v1/admin/agent-deployments') or request.url.path.startswith('/api/v1/admin/assets') or request.url.path.startswith('/api/v1/admin/asset-deployments') or request.url.path.startswith('/api/v1/admin/builder/') or request.url.path.startswith('/api/v1/published-agents/') or request.url.path.startswith('/api/v1/published-agent-runs/') or request.url.path.startswith('/api/v1/tools/') or request.url.path.startswith('/api/v1/admin/tool-approvals') or request.url.path.startswith('/api/v1/admin/tools/') or request.url.path.startswith('/api/v1/admin/workflow-approvals') or request.url.path.startswith('/api/v1/workflows/') or request.url.path.startswith('/api/v1/use-cases/') or
                (request.url.path.startswith('/api/v1/runs/') and request.url.path.endswith('/cancel'))):
            # Bound the actual stream before JSON/Pydantic parsing; Content-Length is not trusted.
            body=bytearray()
            async for chunk in request.stream():
                if len(body)+len(chunk)>32768:
                    return response(request,error=AppError('PAYLOAD_TOO_LARGE',413))
                body.extend(chunk)
            request._body=bytes(body)
        if request.method=='POST' and (request.url.path in ('/api/v1/admin/documents','/api/v1/documents') or (request.url.path.startswith('/api/v1/admin/documents/') and request.url.path.endswith('/versions'))):
            body=bytearray()
            async for chunk in request.stream():
                if len(body)+len(chunk)>147456:return response(request,error=AppError('PAYLOAD_TOO_LARGE',413))
                body.extend(chunk)
            request._body=bytes(body)
        return await call_next(request)

    @app.exception_handler(AppError)
    async def application_error(request, error):
        return response(request, error=error)

    @app.exception_handler(psycopg.Error)
    async def storage_error(request, error):
        return response(request, error=AppError('STORAGE_UNAVAILABLE', 503))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        allowed = {'login_id', 'password','user_id','active','role','expected_revision','cursor','limit','agent_key','name','description','instructions','enabled','local_cap_krw','allocated_cap_krw','period','client_send_id','conversation_id','client_conversation_id','prompt','run_id','document_refs','document_ref','bullet_count','document_id','version_id'}
        fields = sorted({str(item['loc'][-1]) if item['loc'][-1] in allowed else 'body' for item in error.errors()})
        return response(request, error=AppError('REQUEST_INVALID', 422), field_paths=fields)

    @app.get('/api/v1/health')
    def health(request: Request):
        return response(request, {'status': 'ok'})

    if not health_only:
        app.include_router(auth_router)
        app.include_router(tenants_router)
        app.include_router(operations_router)
        app.include_router(approvals_router)
        app.include_router(assets_router)
        app.include_router(builder_router)
        app.include_router(builder_profiles_router)
        app.include_router(builder_trial_router)
        app.include_router(builder_evaluations_router)
        app.include_router(builder_shares_router)
        app.include_router(asset_deployments_router)
        app.include_router(published_agents_router)
        app.include_router(catalog_router)
        app.include_router(conversations_router)
        app.include_router(feedback_router)
        app.include_router(stream_router)
        app.include_router(documents_router)
        app.include_router(user_documents_router)
        app.include_router(share_router)
        app.include_router(evidence_router)
        app.include_router(summary_router)
        app.include_router(models_router)
        app.include_router(data_imports_router)
        app.include_router(tools_router)
        app.include_router(workflows_router)
        app.include_router(workflow_approvals_router)
        app.include_router(guardrails_router)
        app.include_router(use_cases_router)
        app.include_router(overview_router)
    return app


def create_health_app() -> FastAPI:
    return create_app(health_only=True)
