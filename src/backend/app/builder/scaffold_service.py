"""Provider-independent orchestration for strict review-only proposals."""
import json
from dataclasses import replace

from app.ai.types import ProviderOutcome
from app.builder.scaffold_prompts import build_scaffold_messages
from app.builder.scaffold_schemas import (
    AgentProposal,
    ScaffoldRequest,
    WorkflowProposal,
    validate_proposal,
)
from app.errors import AppError


class ScaffoldGenerationService:
    """Run one already-admitted proposal ticket through the central AI Gateway.

    Admission, owner-scoped persistence, idempotency and receipt settlement are
    deliberately supplied by the repository/API boundary. This class never
    creates an asset, starts a trial, invokes a Tool, or publishes a result.
    """

    def __init__(self, gateway):
        self.gateway = gateway

    async def generate(self, ticket, request: ScaffoldRequest) -> AgentProposal | WorkflowProposal:
        if ticket.task_kind != "builder_scaffold":
            raise AppError("EXECUTION_BLOCKED", 403)
        # RunTicket is frozen because its worker and verified run form the
        # execution capability. Replace only the immutable prompt payload.
        request_ticket = replace(ticket, messages=build_scaffold_messages(request))
        outcome: ProviderOutcome = await self.gateway.execute(request_ticket, self._discard_delta)
        if outcome.body is None or outcome.safe_error_code is not None:
            raise AppError(outcome.safe_error_code or "PROVIDER_ERROR", 503)
        try:
            payload = json.loads(outcome.body)
            return validate_proposal(request.target, payload)
        except (ValueError, TypeError, UnicodeError):
            raise AppError("SCAFFOLD_PROPOSAL_INVALID", 502) from None

    @staticmethod
    async def _discard_delta(_text: str) -> None:
        # AiGateway streams only private deltas; proposal UIs receive the final
        # body only after usage settlement and strict schema validation.
        return None
