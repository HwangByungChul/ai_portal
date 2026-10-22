"""Provider-backed, metered generation for private review-only proposals."""
import json
import secrets
from dataclasses import dataclass, field
from types import SimpleNamespace
from uuid import UUID

from app.ai.gateway import AiGateway
from app.ai.repository import ExecutionError
from app.builder.scaffold_prompts import build_scaffold_messages
from app.builder.scaffold_schemas import AgentProposal, ScaffoldRequest, validate_proposal
from app.errors import AppError


@dataclass(frozen=True)
class ScaffoldTicket:
    ctx: object = field(repr=False)
    proposal_id: UUID
    trace_id: UUID
    worker: str = field(repr=False)
    messages: list = field(repr=False)
    model_id: str = "gpt-4o-mini"
    task_kind: str = "builder_scaffold"
    mode: str = "mock"
    run: object = field(default=None, repr=False)


class ScaffoldGenerationService:
    """Use the central Gateway but reserve and settle a non-conversation call."""

    def __init__(self, gateway: AiGateway, repository, guardrails, documents, mode):
        self.gateway = gateway
        self.repository = repository
        self.guardrails = guardrails
        self.documents = documents
        self.mode = mode

    async def generate(self, ctx, proposal_id, trace_id, revision, request: ScaffoldRequest):
        try:
            messages = build_scaffold_messages(request)
            await self.guardrails.inspect(ctx, messages[-1]["content"], direction="input", trace_id=trace_id)
            if request.document_refs:
                refs = [ref.model_dump(mode="json") for ref in request.document_refs]
                await self.documents.allowed(ctx, refs, self.mode)
            ticket = ScaffoldTicket(ctx, proposal_id, trace_id, secrets.token_urlsafe(32),
                messages, mode=self.mode,
                run=SimpleNamespace(tenant_id=ctx.tenant_id, run_id=None, epoch=1))
            outcome = await self.gateway.execute(ticket, self._discard_delta)
            if outcome.safe_error_code or outcome.body is None:
                code = outcome.safe_error_code or "PROVIDER_ERROR"
                raise AppError(code, 503)
            payload = validate_proposal(request.target, json.loads(outcome.body))
            if isinstance(payload, AgentProposal):
                supplied = {(ref.document_id, ref.version_id) for ref in request.document_refs}
                if any((ref.document_id, ref.version_id) not in supplied for ref in payload.profile.document_refs):
                    raise ValueError("SCAFFOLD_PROPOSAL_INVALID")
            if request.document_refs:
                await self.documents.allowed(ctx, refs, self.mode)
            return await self.repository.complete(ctx, proposal_id, revision, payload.model_dump(mode="json"))
        except AppError as error:
            code = error.code if error.code in {
                "GUARDRAIL_INPUT_BLOCKED", "GUARDRAIL_OUTPUT_BLOCKED", "PROVIDER_ERROR",
                "PROVIDER_CONFIGURATION_REQUIRED", "MODEL_NOT_PERMITTED", "LEDGER_UNAVAILABLE",
                "USAGE_INVALID", "PROJECT_STOPPED", "QUOTA_EXCEEDED", "CAPACITY_BUSY",
                "POLICY_CHANGED", "EXECUTION_BLOCKED", "EXECUTION_INTERRUPTED",
            } else "SCAFFOLD_PROPOSAL_INVALID"
            try:
                await self.repository.fail(ctx, proposal_id, revision, code)
            except Exception:
                pass
            raise
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            await self.repository.fail(ctx, proposal_id, revision, "SCAFFOLD_PROPOSAL_INVALID")
            raise AppError("SCAFFOLD_PROPOSAL_INVALID", 502) from None
        except ExecutionError as error:
            try:
                await self.repository.fail(ctx, proposal_id, revision, error.code)
            except Exception:
                pass
            raise AppError(error.code, 503) from None

    @staticmethod
    async def _discard_delta(_text):
        return None
