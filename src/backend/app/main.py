from contextlib import asynccontextmanager
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


def create_app(settings: Settings | None = None, *, health_only: bool = False) -> FastAPI:
    settings = settings or Settings()
    if not health_only:
        settings.require_auth_configuration()
        if settings.execution_enabled:settings.require_execution_configuration()

    @asynccontextmanager
    async def lifespan(app):
        if settings.web_dsn is None:
            app.state.pool = None
            yield
        else:
            async with open_web_pool(settings.web_dsn.get_secret_value()) as pool:
                app.state.pool = pool
                if not health_only:
                    app.state.auth = AuthService(pool, settings)
                app.state.execution=None
                if not health_only and settings.execution_enabled:
                    validate_general_input('질문에 답해 주세요.',[],'준비 확인')
                    async with open_meter_pool(settings.meter_dsn.get_secret_value()) as meter:
                        provider=OpenAIProvider(settings.openai_api_key.get_secret_value()) if settings.mode=='real' else MockProvider()
                        manager=ExecutionManager(CallRepository(pool,meter,settings.budget_period),provider,settings.mode,StreamHub())
                        try:
                            await manager.start();app.state.execution=manager
                            yield
                        finally:await manager.close()
                else:yield

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
    return app


def create_health_app() -> FastAPI:
    return create_app(health_only=True)
