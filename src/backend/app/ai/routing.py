"""Model Routing: Dynamically routes execution to the approved provider based on ModelRef."""
from typing import Callable, Any
from app.ai.model_registry import ModelRef, ModelRegistry, GLOBAL_REGISTRY
from app.ai.providers import Provider, MockProvider, OpenAIProvider
from app.errors import AppError

class ModelRouter:
    def __init__(
        self,
        registry: ModelRegistry | None = None,
        api_key_resolver: Callable[[str], str | None] | None = None,
        execution_mode: str = "mock",
    ):
        if execution_mode not in ("mock", "real"):
            raise ValueError("EXECUTION_MODE_INVALID")
        self.registry = registry or GLOBAL_REGISTRY
        self.api_key_resolver = api_key_resolver or (lambda ref: None)
        self.execution_mode = execution_mode
        self._provider_cache: dict[str, Provider] = {}

    def get_provider(self, model: ModelRef) -> Provider:
        # A mock environment must never use a configured real key.
        if self.execution_mode == "mock":
            return MockProvider()
        # The current confirmed-dispatch SQL price snapshot supports only
        # gpt-4o-mini. Other real models require a versioned ledger migration.
        if model.provider_key == "openai" and model.model_name != "gpt-4o-mini":
            raise AppError("MODEL_NOT_PERMITTED", 403)
        # 1. In real mode, mock provider is forbidden
        if self.execution_mode == "real" and model.provider_key == "mock":
            raise AppError("MODEL_NOT_PERMITTED", 403)

        if model.provider_key == "mock":
            return MockProvider()

        if model.provider_key == "openai":
            key = self.api_key_resolver(model.credential_ref)
            # In real mode, missing key MUST fail explicitly with 503, never silently fallback to mock
            if self.execution_mode == "real" and not key:
                raise AppError("PROVIDER_CONFIGURATION_REQUIRED", 503)

            if not key:
                return MockProvider()

            if model.model_id in self._provider_cache:
                return self._provider_cache[model.model_id]

            provider = OpenAIProvider(api_key=key)
            self._provider_cache[model.model_id] = provider
            return provider

        raise AppError("PROVIDER_UNSUPPORTED", 500)

    def route(self, model_id: str | None = None) -> tuple[ModelRef, Provider]:
        model = self.registry.resolve(model_id)
        provider = self.get_provider(model)
        return model, provider

    async def close(self):
        providers=list(self._provider_cache.values())
        self._provider_cache.clear()
        for provider in providers:
            await provider.close()


def build_model_router(settings):
    def resolve_secret(reference):
        if reference != "OPENAI_API_KEY" or settings.openai_api_key is None:
            return None
        return settings.openai_api_key.get_secret_value().strip() or None
    return ModelRouter(execution_mode=settings.mode, api_key_resolver=resolve_secret)

# Compatibility for pure fixture consumers only; runtime uses settings injection.
GLOBAL_ROUTER = ModelRouter()
