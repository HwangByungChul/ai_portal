from datetime import date, datetime, timedelta
import re
from zoneinfo import ZoneInfo
from typing import Annotated
from fastapi import APIRouter, Request, Query
from app.auth.guards import check_transport, cookie_token
from app.db import tenant_transaction
from app.errors import AppError, response
from app.tenants.routes import context as tenant_context
import psycopg

router = APIRouter(prefix="/api/v1/admin/overview")

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_query_keys(request: Request, allowed: set[str]) -> None:
    for k in request.query_params:
        if k not in allowed or len(request.query_params.getlist(k)) != 1:
            raise AppError("REQUEST_INVALID", 422)


@router.get("")
async def get_overview(
    request: Request,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
):
    validate_query_keys(request, {"date_from", "date_to"})
    ctx = await tenant_context(request)

    # Authority guard: PADMIN or TADMIN required
    if ctx.effective_role not in ("PADMIN", "TADMIN"):
        raise AppError("MANAGEMENT_DENIED", 403)

    today = datetime.now(ZoneInfo('Asia/Seoul')).date()
    if date_from is None and date_to is None:
        parsed_to = today
        parsed_from = today - timedelta(days=6)
    else:
        if date_from is None or date_to is None:
            raise AppError("REQUEST_INVALID", 422)
        if not DATE_PATTERN.match(date_from) or not DATE_PATTERN.match(date_to):
            raise AppError("REQUEST_INVALID", 422)
        try:
            parsed_from = datetime.strptime(date_from, "%Y-%m-%d").date()
            parsed_to = datetime.strptime(date_to, "%Y-%m-%d").date()
        except ValueError:
            raise AppError("REQUEST_INVALID", 422) from None

    if parsed_to < parsed_from or (parsed_to - parsed_from).days >= 31:
        raise AppError("REQUEST_INVALID", 422)

    pool = getattr(request.app.state, "pool", None)
    if not pool:
        raise AppError('STORAGE_UNAVAILABLE',503)

    try:
        async with tenant_transaction(pool, ctx) as conn:
            row = await (await conn.execute(
                "SELECT security.admin_overview_read(%s, %s, %s, %s) AS data",
                (ctx.session_id, ctx.tenant_id, parsed_from, parsed_to)
            )).fetchone()
            return response(request, row["data"])
    except psycopg.Error as error:
        if error.sqlstate == "A0403":
            raise AppError("MANAGEMENT_DENIED", 403) from None
        if error.sqlstate == "A0422":
            raise AppError("REQUEST_INVALID", 422) from None
        raise AppError("STORAGE_UNAVAILABLE", 503) from None
