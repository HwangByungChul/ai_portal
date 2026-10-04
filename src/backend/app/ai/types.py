from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

Operation = Literal['generate_general', 'generate_rag', 'embed_query', 'embed_document']
Mode = Literal['mock', 'real']

@dataclass(frozen=True)
class VerifiedRun:
    tenant_id: UUID
    run_id: UUID
    owner_user_id: UUID
    origin_session_id: UUID
    epoch: int
    config_revision: int
    mode: Mode

@dataclass(frozen=True)
class DispatchClaim:
    call_id: UUID
    epoch: int
    claim: str = field(repr=False)

@dataclass(frozen=True)
class UsageReceipt:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    observed_model: str
    observed_tier: str
    provider_request_id: str | None = field(repr=False)

@dataclass(frozen=True)
class ProviderOutcome:
    body: str | None = field(repr=False)
    receipt: UsageReceipt | None
    end_status: Literal['observed', 'unknown']
    safe_error_code: str | None

@dataclass(frozen=True)
class RunView:
    run_id: UUID
    conversation_id: UUID
    state: str
    revision: int
    execution_mode: Mode
    content_status: str
    usage_status: str
    result: str | None = field(repr=False)
