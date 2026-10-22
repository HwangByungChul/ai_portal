"""Owner-only proposal admission and retention primitives.

This repository does not perform provider dispatch. A dedicated metered,
non-conversation call capability must exist before an admitted request can be
generated; using the normal conversation ledger would persist prompt content
in the user's conversation history.
"""
import psycopg
from psycopg.types.json import Jsonb

from app.db import tenant_transaction
from app.errors import AppError
from app.operations.repository import OperationsRepository


class ScaffoldRepository:
    def __init__(self, pool):
        self.pool = pool

    async def admit(self, ctx, request, *, model_id, policy_revision, budget_period):
        payload = request.model_dump(mode="json", exclude={"client_request_id", "target"})
        try:
            async with tenant_transaction(self.pool, ctx) as conn:
                row = await (await conn.execute(
                    "SELECT security.builder_scaffold_admit(%s,%s,%s,%s,%s,%s,%s,%s) AS data",
                    (ctx.session_id, ctx.tenant_id, request.client_request_id, request.target,
                     Jsonb(payload), model_id, str(policy_revision), budget_period),
                )).fetchone()
            return row["data"]
        except (psycopg.Error, ValueError) as error:
            self._translate(error)

    async def read(self, ctx, proposal_id):
        try:
            async with tenant_transaction(self.pool, ctx) as conn:
                row = await (await conn.execute(
                    "SELECT security.builder_scaffold_read(%s,%s,%s) AS data",
                    (ctx.session_id, ctx.tenant_id, proposal_id),
                )).fetchone()
            return row["data"]
        except (psycopg.Error, ValueError) as error:
            self._translate(error)

    async def discard(self, ctx, proposal_id, expected_revision):
        try:
            async with tenant_transaction(self.pool, ctx) as conn:
                row = await (await conn.execute(
                    "SELECT security.builder_scaffold_discard(%s,%s,%s,%s) AS data",
                    (ctx.session_id, ctx.tenant_id, proposal_id, expected_revision),
                )).fetchone()
            return row["data"]
        except (psycopg.Error, ValueError) as error:
            self._translate(error)

    @staticmethod
    def _translate(error):
        if isinstance(error, psycopg.Error):
            code = {
                "A0401": ("AUTH_REQUIRED", 401),
                "A0403": ("MANAGEMENT_DENIED", 403),
                "A0404": ("RESOURCE_NOT_FOUND", 404),
                "A0409": ("REVISION_CONFLICT", 409),
                "A0422": ("REQUEST_INVALID", 422),
            }.get(error.sqlstate)
            if code:
                raise AppError(*code) from None
        OperationsRepository.translate(error)
