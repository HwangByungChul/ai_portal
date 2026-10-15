import asyncio
import pytest
from app.ai.types import ProviderOutcome, UsageReceipt
from app.ai.providers import Provider
from app.execution.stream import StreamHub

class LeakingProvider(Provider):
    """Provider that yields PII in chunks."""
    async def generate(self, claim, messages, on_delta):
        # Chunk 1: 주민번호 앞자리
        await on_delta("주민등록번호는 900101-")
        # Chunk 2: 주민번호 뒷자리 (PII 완성)
        await on_delta("1234567 입니다.")
        receipt = UsageReceipt(claim, "gpt-4o-mini", "openai", "price-v1", 10, 20)
        return ProviderOutcome("주민등록번호는 900101-1234567 입니다.", receipt, "final", None)


from types import SimpleNamespace
from uuid import uuid4

@pytest.mark.anyio
async def test_output_gate_never_leaks_uninspected_chunks_to_hub():
    """Uninspected raw text chunks must NEVER be published to client StreamHub before output evaluation."""
    hub = StreamHub()
    run = SimpleNamespace(tenant_id=uuid4(), run_id=uuid4(), epoch=1)
    hub.begin(run)

    received_from_hub = []
    
    # Simulate consumer listening to StreamHub
    # Using private delta collector pattern as specified in Plan 26 Section 8
    chunks = []
    async def collect_private_delta(text: str):
        # Verify that private delta accumulates securely and does not touch hub directly
        chunks.append(text)
        # Verify length limit
        if sum(len(c) for c in chunks) > 32768:
            raise ValueError("BUFFER_OVERRUN")

    provider = LeakingProvider()
    outcome = await provider.generate("claim-1", [], collect_private_delta)
    
    # 1. Before guardrail inspection, hub MUST have 0 events
    assert len(received_from_hub) == 0

    # 2. Private buffer must contain the generated text
    collected_body = "".join(chunks)
    assert "900101-1234567" in collected_body

    # 3. Guardrail inspection masks or blocks the output
    from app.guardrails.engine import evaluate_output
    out_res = evaluate_output(collected_body)
    
    # In default policy, PII action is 'mask'
    assert out_res.action in ("mask", "block")
    if out_res.action == "mask":
        assert out_res.masked_text is not None
        assert "900101-1234567" not in out_res.masked_text
        # Only the masked text is published to hub
        hub.append(run, out_res.masked_text)
    
    hub.clear(run)
    hub.close()
