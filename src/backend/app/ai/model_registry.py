"""Model Registry: Server-controlled model metadata, pricing, capabilities, and secret references."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from app.errors import AppError

@dataclass(frozen=True)
class ModelRef:
    model_id: str
    provider_key: str
    model_name: str
    credential_ref: str
    pricing_version: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    context_window: int
    max_output_tokens: int
    enabled: bool
    capabilities: tuple[str, ...]

    def to_public_dict(self) -> dict[str, Any]:
        """Never expose credential_ref to clients."""
        return {
            "model_id": self.model_id,
            "provider_key": self.provider_key,
            "model_name": self.model_name,
            "pricing_version": self.pricing_version,
            "input_usd_per_million": str(self.input_usd_per_million),
            "output_usd_per_million": str(self.output_usd_per_million),
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "enabled": self.enabled,
            "capabilities": list(self.capabilities),
        }

APPROVED_MODELS: dict[str, ModelRef] = {
    "gpt-4o-mini": ModelRef(
        model_id="gpt-4o-mini",
        provider_key="openai",
        model_name="gpt-4o-mini",
        credential_ref="OPENAI_API_KEY",
        pricing_version="price-20261004-v1",
        input_usd_per_million=Decimal("0.15"),
        output_usd_per_million=Decimal("0.60"),
        context_window=128000,
        max_output_tokens=16384,
        enabled=True,
        capabilities=("chat", "rag", "structured", "streaming"),
    ),
    "gpt-4o": ModelRef(
        model_id="gpt-4o",
        provider_key="openai",
        model_name="gpt-4o",
        credential_ref="OPENAI_API_KEY",
        pricing_version="price-20261004-v1",
        input_usd_per_million=Decimal("2.50"),
        output_usd_per_million=Decimal("10.00"),
        context_window=128000,
        max_output_tokens=16384,
        enabled=True,
        capabilities=("chat", "rag", "structured", "streaming"),
    ),
    "mock-fast": ModelRef(
        model_id="mock-fast",
        provider_key="mock",
        model_name="mock-fast",
        credential_ref="MOCK",
        pricing_version="price-20261004-v1",
        input_usd_per_million=Decimal("0.15"),
        output_usd_per_million=Decimal("0.60"),
        context_window=128000,
        max_output_tokens=4096,
        enabled=True,
        capabilities=("chat", "rag"),
    ),
    "mock-disabled": ModelRef(
        model_id="mock-disabled",
        provider_key="mock",
        model_name="mock-disabled",
        credential_ref="MOCK",
        pricing_version="price-20261004-v1",
        input_usd_per_million=Decimal("1.00"),
        output_usd_per_million=Decimal("2.00"),
        context_window=32000,
        max_output_tokens=2048,
        enabled=False,
        capabilities=("chat",),
    ),
}

DEFAULT_MODEL_ID = "gpt-4o-mini"

class ModelRegistry:
    def __init__(self, models: dict[str, ModelRef] | None = None):
        self._models = dict(models or APPROVED_MODELS)

    def get(self, model_id: str) -> ModelRef | None:
        return self._models.get(model_id)

    def resolve(self, model_id: str | None = None) -> ModelRef:
        """Resolve requested model or fallback to default."""
        mid = DEFAULT_MODEL_ID if (not model_id or model_id in ("default_general", "default_rules_rag")) else model_id
        model = self.get(mid)
        if model is None:
            raise AppError("MODEL_NOT_FOUND", 400)
        if not model.enabled:
            raise AppError("MODEL_NOT_PERMITTED", 403)
        return model

    def list_public(self) -> list[dict[str, Any]]:
        return [m.to_public_dict() for m in self._models.values() if m.enabled]

    def list_all_admin(self) -> list[dict[str, Any]]:
        return [m.to_public_dict() for m in self._models.values()]

GLOBAL_REGISTRY = ModelRegistry()
