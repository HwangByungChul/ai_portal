from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from app.config import Settings
from app.db import open_web_pool


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        if settings.web_dsn is None:
            app.state.pool = None  # Health-only process; no authentication routes yet.
            yield
        else:
            async with open_web_pool(settings.web_dsn.get_secret_value()) as pool:
                app.state.pool = pool
                yield

    app = FastAPI(title='AI Platform MVP', version='0.1.0',lifespan=lifespan)

    @app.get('/api/v1/health')
    def health() -> JSONResponse:
        request_id = str(uuid4())
        return JSONResponse(
            {'data': {'status': 'ok'}, 'meta': {'request_id': request_id,'tenant_id': None,
             'server_time': datetime.now(timezone.utc).isoformat()}},
            headers={'Cache-Control': 'no-store', 'X-Request-ID': request_id},
        )

    return app
