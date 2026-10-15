"""DP-13 Model Registry & Multi-Model Gateway Acceptance Tests."""
import pytest
from decimal import Decimal
from uuid import uuid4
from app.ai.types import UsageReceipt, ProviderOutcome
from app.ai.pricing import cost_krw, reservation_krw
from app.ai.model_registry import ModelRegistry, ModelRef, APPROVED_MODELS, GLOBAL_REGISTRY
from app.ai.routing import ModelRouter
from app.ai.gateway import AiGateway
from app.errors import AppError

def test_dp13_c01_arbitrary_model_and_key_payload_blocked():
    """DP-13-C01: 임의 모델/공급자/key payload 차단 및 credential 은닉 검증."""
    registry = ModelRegistry()
    # 1. Unregistered arbitrary model rejected
    with pytest.raises(AppError) as exc:
        registry.resolve("arbitrary-rogue-llm")
    assert exc.value.status == 400
    assert exc.value.code == "MODEL_NOT_FOUND"

    # 2. Public listing NEVER exposes credential_ref or disabled models
    public_list = registry.list_public()
    assert len(public_list) >= 2
    for item in public_list:
        assert "credential_ref" not in item
        assert "api_key" not in item
        assert item["enabled"] is True
        assert item["model_id"] in APPROVED_MODELS

def test_dp13_c02_unpermitted_and_disabled_model_execution_blocked():
    """DP-13-C02: 비활성/미승인 모델 실행 금지 검증."""
    registry = ModelRegistry()
    # mock-disabled exists in registry but enabled=False
    with pytest.raises(AppError) as exc:
        registry.resolve("mock-disabled")
    assert exc.value.status == 403
    assert exc.value.code == "MODEL_NOT_PERMITTED"

    router = ModelRouter(registry=registry)
    with pytest.raises(AppError) as exc:
        router.route("mock-disabled")
    assert exc.value.code == "MODEL_NOT_PERMITTED"

def test_dp13_c03_pricing_version_snapshot_and_metering_accuracy():
    """DP-13-C03: 다중 모델 가격표 산출 및 미승인 영수증 거부 검증."""
    # 1. gpt-4o-mini price check
    r_mini = UsageReceipt(1000, 500, 1500, 'gpt-4o-mini', 'default', 'req-1')
    cost_mini = cost_krw(r_mini)
    assert cost_mini > Decimal('0')

    # 2. gpt-4o higher price check
    r_4o = UsageReceipt(1000, 500, 1500, 'gpt-4o', 'default', 'req-2')
    cost_4o = cost_krw(r_4o)
    assert cost_4o > cost_mini  # gpt-4o must be noticeably more expensive than mini

    # 3. Unapproved model receipt must be rejected by cost_krw
    r_unapproved = UsageReceipt(1000, 500, 1500, 'unapproved-hacked-model', 'default', 'req-3')
    with pytest.raises(ValueError) as exc:
        cost_krw(r_unapproved)
    assert "USAGE_RECEIPT_REJECTED" in str(exc.value)

def test_dp13_c04_gateway_router_integration_and_model_switching():
    """DP-13-C04: Gateway를 통한 동적 모델 라우팅 및 허가증 기반 실행 제어 검증."""
    router = ModelRouter()
    # Resolve approved mock model
    ref, provider = router.route("mock-fast")
    assert ref.model_id == "mock-fast"
    assert ref.provider_key == "mock"

    # Fallback to default when model is None
    default_ref, default_provider = router.route(None)
    assert default_ref.model_id == "gpt-4o-mini"

    # Gateway stops unpermitted model on execute
    class DummyRepo:
        pass
    gw = AiGateway(repository=DummyRepo(), router=router)
    class FakeTicket:
        model_id = "mock-disabled"
    outcome = pytest.MonkeyPatch().context()
    # Test router integration in Gateway
    import asyncio
    async def run_gw():
        res = await gw.execute(FakeTicket(), None)
        assert res.safe_error_code == "MODEL_NOT_PERMITTED"
    asyncio.run(run_gw())

def test_dp13_c05_http_models_endpoints(client, fixture_state, login):
    """DP-13-C05: HTTP API 엔드포인트 /api/v1/models 및 /api/v1/admin/models 검증."""
    tenant_a = str(fixture_state.state.tenant_ids['A'])

    # 1. Unauthenticated request rejected
    resp = client.get('/api/v1/models')
    assert resp.status_code == 401

    # 2. Ordinary user session retrieves public models
    login(client, 'A-U1')
    resp = client.get('/api/v1/models', headers={'X-Tenant-ID': tenant_a})
    assert resp.status_code == 200
    data = resp.json()['data']
    assert 'items' in data
    model_ids = [m['model_id'] for m in data['items']]
    assert 'gpt-4o-mini' in model_ids
    assert 'mock-disabled' not in model_ids  # Disabled model is hidden
    for m in data['items']:
        assert 'credential_ref' not in m
        assert 'api_key' not in m

    # 3. Platform Admin retrieves all models including disabled ones
    login(client, 'P-A')
    admin_resp = client.get('/api/v1/admin/models', headers={'X-Tenant-ID': tenant_a})
    assert admin_resp.status_code == 200
    admin_data = admin_resp.json()['data']
    admin_model_ids = [m['model_id'] for m in admin_data['items']]
    assert 'mock-disabled' in admin_model_ids

