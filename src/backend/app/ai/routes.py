"""Model Registry HTTP endpoints."""
from fastapi import APIRouter, Request
from app.tenants.routes import context
from app.ai.model_registry import GLOBAL_REGISTRY
from app.errors import AppError, response

models_router = APIRouter(prefix="/api/v1")

@models_router.get("/models")
async def list_models(request: Request):
    """List approved models available for user selection."""
    await context(request)
    return response(request, {"items": GLOBAL_REGISTRY.list_public()})

@models_router.get("/admin/models")
async def list_admin_models(request: Request):
    """List all models including disabled ones for platform administrators."""
    ctx = await context(request)
    if ctx.effective_role != 'PADMIN':
        raise AppError("REQUEST_FORBIDDEN", 403)
    return response(request, {"items": GLOBAL_REGISTRY.list_all_admin()})
