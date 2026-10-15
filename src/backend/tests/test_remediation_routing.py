import pytest
from app.ai.model_registry import ModelRegistry, ModelRef
from app.ai.routing import ModelRouter
from app.ai.providers import MockProvider, OpenAIProvider
from app.errors import AppError

def test_real_mode_missing_key_raises_503():
    """In real mode, if API key is missing, never fallback to MockProvider; raise 503."""
    registry = ModelRegistry()
    router = ModelRouter(registry=registry, api_key_resolver=lambda ref: None, execution_mode="real")
    
    with pytest.raises(AppError) as exc:
        router.route("gpt-4o-mini")
    assert exc.value.status == 503
    assert exc.value.code == "PROVIDER_CONFIGURATION_REQUIRED"


def test_real_mode_mock_provider_blocked_403():
    """In real mode, mock provider models must not be permitted; raise 403."""
    registry = ModelRegistry()
    router = ModelRouter(registry=registry, api_key_resolver=lambda ref: None, execution_mode="real")
    
    with pytest.raises(AppError) as exc:
        router.route("mock-fast")
    assert exc.value.status == 403
    assert exc.value.code == "MODEL_NOT_PERMITTED"


def test_mock_mode_allows_mock_and_fallback():
    """In mock mode, mock model returns MockProvider and missing key returns MockProvider."""
    registry = ModelRegistry()
    router = ModelRouter(registry=registry, api_key_resolver=lambda ref: None, execution_mode="mock")
    
    model_mock, provider_mock = router.route("mock-fast")
    assert isinstance(provider_mock, MockProvider)
    
    model_real, provider_real = router.route("gpt-4o-mini")
    assert isinstance(provider_real, MockProvider)


def test_real_mode_with_key_returns_openai_provider():
    """In real mode with valid key, returns OpenAIProvider."""
    registry = ModelRegistry()
    router = ModelRouter(registry=registry, api_key_resolver=lambda ref: "sk-valid-test-key", execution_mode="real")
    
    model, provider = router.route("gpt-4o-mini")
    assert isinstance(provider, OpenAIProvider)
    assert model.model_id == "gpt-4o-mini"
