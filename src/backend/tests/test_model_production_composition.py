import pytest
from types import SimpleNamespace
from pydantic import SecretStr
from app.ai import routing
from app.ai.providers import MockProvider
from app.errors import AppError
from app.execution.manager import ExecutionManager

@pytest.mark.anyio
async def test_mock_mode_never_constructs_real_client_even_with_key(monkeypatch):
    def forbidden(**kwargs): raise AssertionError("real client constructed in mock mode")
    monkeypatch.setattr(routing, "OpenAIProvider", forbidden)
    router=routing.ModelRouter(execution_mode="mock",api_key_resolver=lambda ref:"synthetic-key")
    assert isinstance(router.route("gpt-4o-mini")[1],MockProvider)

def test_main_settings_router_uses_real_mode_without_fallback():
    assert hasattr(routing,"build_model_router")
    router=routing.build_model_router(SimpleNamespace(mode="real",openai_api_key=None))
    manager=ExecutionManager(None,None,"real",None,router=router)
    with pytest.raises(AppError) as caught: manager.gateway.router.route("gpt-4o-mini")
    assert caught.value.code=="PROVIDER_CONFIGURATION_REQUIRED"

def test_existing_ledger_rejects_more_expensive_model_before_client(monkeypatch):
    def forbidden(**kwargs): raise AssertionError("client constructed before ledger contract")
    monkeypatch.setattr(routing,"OpenAIProvider",forbidden)
    router=routing.ModelRouter(execution_mode="real",api_key_resolver=lambda ref:"synthetic-key")
    with pytest.raises(AppError) as caught: router.route("gpt-4o")
    assert caught.value.code=="MODEL_NOT_PERMITTED"

def test_manager_honors_explicit_provider_without_global_router():
    provider=object()
    manager=ExecutionManager(None,provider,"real",None)
    assert manager.gateway.provider is provider
    assert manager.gateway.router is None

@pytest.mark.anyio
async def test_settings_key_reference_and_router_shutdown(monkeypatch):
    assert hasattr(routing,"build_model_router")
    instances=[]
    class Provider:
        def __init__(self,api_key):self.closed=False;instances.append(self)
        async def close(self):self.closed=True
    monkeypatch.setattr(routing,"OpenAIProvider",Provider)
    router=routing.build_model_router(SimpleNamespace(mode="real",openai_api_key=SecretStr("synthetic-key")))
    assert router.api_key_resolver("OTHER_KEY") is None
    assert router.route("gpt-4o-mini")[1] is router.route("gpt-4o-mini")[1]
    await router.close()
    assert len(instances)==1 and instances[0].closed
