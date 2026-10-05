from contextlib import asynccontextmanager,AsyncExitStack
from uuid import uuid4
import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from app.auth.routes import router as auth_router
from app.auth.service import AuthService
from app.tenants.routes import router as tenants_router
from app.operations.routes import router as operations_router
from app.conversations.routes import router as conversations_router
from app.config import Settings
from app.db import open_web_pool,open_meter_pool
from app.ai.repository import CallRepository
from app.ai.providers import MockProvider,OpenAIProvider
from app.ai.token_limits import validate_general_input
from app.execution.manager import ExecutionManager
from app.execution.stream import StreamHub,router as stream_router
from app.errors import AppError, response
from app.documents.routes import router as documents_router
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage
from app.documents.embedding import EmbeddingGateway,MockEmbeddingProvider,OpenAIEmbeddingProvider
from app.documents.worker import DocumentWorker
from app.documents.manager import DocumentManager
from app.db import open_index_pool


def create_app(settings: Settings | None = None, *, health_only: bool = False) -> FastAPI:
    settings = settings or Settings()
    if not health_only:
        settings.require_auth_configuration()
        if settings.execution_enabled:settings.require_execution_configuration()
        if settings.index_enabled:settings.require_index_configuration()

    @asynccontextmanager
    async def lifespan(app):
        async with AsyncExitStack() as stack:
            app.state.pool=None;app.state.execution=None;app.state.document_manager=None
            if settings.web_dsn is not None:
                pool=await stack.enter_async_context(open_web_pool(settings.web_dsn.get_secret_value()));app.state.pool=pool
                if not health_only:
                    app.state.auth=AuthService(pool,settings)
                    app.state.documents=DocumentRepository(pool,SourceStorage(settings.source_root),settings.login_hmac_secret.get_secret_value(),settings.mode)
                    if settings.execution_enabled or settings.index_enabled:
                        meter=await stack.enter_async_context(open_meter_pool(settings.meter_dsn.get_secret_value()))
                    if settings.execution_enabled:
                        validate_general_input('질문에 답해 주세요.',[],'준비 확인')
                        provider=OpenAIProvider(settings.openai_api_key.get_secret_value()) if settings.mode=='real' else MockProvider()
                        manager=ExecutionManager(CallRepository(pool,meter,settings.budget_period),provider,settings.mode,StreamHub())
                        await manager.start();stack.push_async_callback(manager.close);app.state.execution=manager
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
        if request.method=='POST' and (request.url.path in ('/api/v1/runs','/api/v1/conversations') or
                (request.url.path.startswith('/api/v1/runs/') and request.url.path.endswith('/cancel'))):
            # Bound the actual stream before JSON/Pydantic parsing; Content-Length is not trusted.
            body=bytearray()
            async for chunk in request.stream():
                if len(body)+len(chunk)>32768:
                    return response(request,error=AppError('PAYLOAD_TOO_LARGE',413))
                body.extend(chunk)
            request._body=bytes(body)
        if request.method=='POST' and (request.url.path=='/api/v1/admin/documents' or (request.url.path.startswith('/api/v1/admin/documents/') and request.url.path.endswith('/versions'))):
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
        allowed = {'login_id', 'password','user_id','active','role','expected_revision','cursor','limit','agent_key','name','description','instructions','enabled','local_cap_krw','allocated_cap_krw','period','client_send_id','conversation_id','client_conversation_id','prompt','run_id','document_refs','document_id','version_id'}
        fields = sorted({str(item['loc'][-1]) if item['loc'][-1] in allowed else 'body' for item in error.errors()})
        return response(request, error=AppError('REQUEST_INVALID', 422), field_paths=fields)

    @app.get('/api/v1/health')
    def health(request: Request):
        return response(request, {'status': 'ok'})

    if not health_only:
        app.include_router(auth_router)
        app.include_router(tenants_router)
        app.include_router(operations_router)
        app.include_router(conversations_router)
        app.include_router(stream_router)
        app.include_router(documents_router)
    return app


def create_health_app() -> FastAPI:
    return create_app(health_only=True)
