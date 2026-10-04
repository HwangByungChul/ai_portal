from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import Settings


def create_app() -> FastAPI:
    Settings()  # Fail closed on an invalid profile; A01 health needs no DB credentials.
    app = FastAPI(title="AI Platform MVP", version="0.1.0")

    @app.get("/api/v1/health")
    def health() -> JSONResponse:
        request_id = str(uuid4())
        return JSONResponse(
            {
                "data": {"status": "ok"},
                "meta": {
                    "request_id": request_id,
                    "tenant_id": None,
                    "server_time": datetime.now(timezone.utc).isoformat(),
                },
            },
            headers={"Cache-Control": "no-store", "X-Request-ID": request_id},
        )

    return app
