from contextlib import asynccontextmanager
from uuid import uuid4
import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from app.auth.routes import router as auth_router
from app.auth.service import AuthService
from app.tenants.routes import router as tenants_router
from app.operations.routes import router as operations_router
from app.config import Settings
from app.db import open_web_pool
from app.errors import AppError, response


def create_app(settings: Settings | None = None, *, health_only: bool = False) -> FastAPI:
    settings = settings or Settings()
    if not health_only:
        settings.require_auth_configuration()

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
                yield

    app = FastAPI(title='AI Platform MVP', version='0.1.0', lifespan=lifespan)
    app.state.settings = settings

    @app.middleware('http')
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        return await call_next(request)

    @app.exception_handler(AppError)
    async def application_error(request, error):
        return response(request, error=error)

    @app.exception_handler(psycopg.Error)
    async def storage_error(request, error):
        return response(request, error=AppError('STORAGE_UNAVAILABLE', 503))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        allowed = {'login_id', 'password','user_id','active','role','expected_revision','cursor','limit','agent_key','name','description','instructions','enabled','local_cap_krw','allocated_cap_krw','period'}
        fields = sorted({str(item['loc'][-1]) if item['loc'][-1] in allowed else 'body' for item in error.errors()})
        return response(request, error=AppError('REQUEST_INVALID', 422), field_paths=fields)

    @app.get('/api/v1/health')
    def health(request: Request):
        return response(request, {'status': 'ok'})

    if not health_only:
        app.include_router(auth_router)
        app.include_router(tenants_router)
        app.include_router(operations_router)
    return app


def create_health_app() -> FastAPI:
    return create_app(health_only=True)
