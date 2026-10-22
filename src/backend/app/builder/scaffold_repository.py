"""Owner-only proposal admission and retention primitives.

This repository does not perform provider dispatch. A dedicated metered,
non-conversation call capability must exist before an admitted request can be
generated; using the normal conversation ledger would persist prompt content
in the user's conversation history.
"""
import psycopg
import secrets
from dataclasses import asdict
from uuid import UUID
from psycopg.types.json import Jsonb

from app.db import tenant_transaction
from app.errors import AppError
from app.operations.repository import OperationsRepository
from app.ai.repository import ExecutionError, DispatchUncertain, digest


class ScaffoldRepository:
    def __init__(self, pool, meter_pool=None, period=None):
        self.pool = pool
        self.meter_pool = meter_pool
        self.period = period

    async def admit(self, ctx, request, *, trace_id, model_id, policy_revision, budget_period):
        payload = request.model_dump(mode="json", exclude={"client_request_id", "target"})
        try:
            async with tenant_transaction(self.pool, ctx) as conn:
                row = await (await conn.execute(
                    "SELECT security.builder_scaffold_admit(%s,%s,%s,%s,%s,%s,%s,%s,%s) AS data",
                    (ctx.session_id, ctx.tenant_id, trace_id, request.client_request_id, request.target,
                     Jsonb(payload), model_id, str(policy_revision), budget_period),
                )).fetchone()
            return row["data"]
        except (psycopg.Error, ValueError) as error:
            self._translate(error)

    async def reserve(self, ticket, fingerprint):
        return await self._worker_rpc(ticket, "builder_scaffold_reserve", (
            ticket.ctx.session_id, ticket.ctx.tenant_id, ticket.proposal_id, self.period,
            ticket.mode, digest(ticket.worker), fingerprint,
        ))

    async def dispatch(self, ticket, call_id):
        from app.ai.types import DispatchClaim
        secret = secrets.token_urlsafe(32)
        claim = DispatchClaim(UUID(call_id), ticket.run.epoch, secret)
        try:
            ok = await self._worker_rpc(ticket, "builder_scaffold_dispatch", (
                ticket.ctx.session_id, ticket.ctx.tenant_id, ticket.proposal_id, call_id,
                self.period, ticket.mode, digest(ticket.worker), digest(secret),
            ))
        except ExecutionError as error:
            if error.code == "LEDGER_UNAVAILABLE":
                raise DispatchUncertain(claim) from None
            raise
        return claim if ok else None

    async def release_unfired(self, ticket, call_id):
        return await self._worker_rpc(ticket, "builder_scaffold_release", (
            ticket.ctx.session_id, ticket.ctx.tenant_id, ticket.proposal_id, call_id, digest(ticket.worker),
        ))

    async def settle(self, ticket, claim, receipt, end_status, invalid=False):
        try:
            async with self.meter_pool.connection() as conn:
                async with conn.transaction():
                    row = await (await conn.execute(
                        "SELECT security.call_meter(%s,%s,%s,%s,%s,%s,%s) AS data",
                        (ticket.ctx.tenant_id, claim.call_id, claim.epoch, digest(claim.claim),
                         Jsonb(asdict(receipt)) if receipt is not None else None, end_status, invalid),
                    )).fetchone()
            return row["data"]
        except (psycopg.Error, ValueError):
            raise ExecutionError("LEDGER_UNAVAILABLE") from None

    async def _worker_rpc(self, ticket, name, args):
        try:
            async with tenant_transaction(self.pool, ticket.ctx) as conn:
                row = await (await conn.execute(
                    "SELECT security." + name + "(" + ",".join(["%s"] * len(args)) + ") AS data", args
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

    async def complete(self, ctx, proposal_id, revision, payload):
        try:
            async with tenant_transaction(self.pool, ctx) as conn:
                row = await (await conn.execute(
                    "SELECT security.builder_scaffold_complete(%s,%s,%s,%s,%s) AS data",
                    (ctx.session_id, ctx.tenant_id, proposal_id, revision, Jsonb(payload)),
                )).fetchone()
            return row["data"]
        except (psycopg.Error, ValueError) as error:
            self._translate(error)

    async def fail(self, ctx, proposal_id, revision, code):
        try:
            async with tenant_transaction(self.pool, ctx) as conn:
                row = await (await conn.execute(
                    "SELECT security.builder_scaffold_fail(%s,%s,%s,%s,%s) AS data",
                    (ctx.session_id, ctx.tenant_id, proposal_id, revision, code),
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
            from app.ai.repository import CODES
            if error.sqlstate in CODES:
                raise ExecutionError(CODES[error.sqlstate]) from None
        OperationsRepository.translate(error)
