"""Unit tests for resilience primitives: RateLimiter and CircuitBreaker."""
import time
import pytest
from app.tools.resilience import CircuitBreaker, ConcurrencyLimiter, TokenBucketRateLimiter


def test_rate_limiter_depletion():
    limiter = TokenBucketRateLimiter(default_max_tokens=3, default_refill_per_sec=0.1)
    tenant = "t1"
    tool = "check_status"

    assert limiter.try_acquire(tenant, tool) is True
    assert limiter.try_acquire(tenant, tool) is True
    assert limiter.try_acquire(tenant, tool) is True
    # 4th attempt exceeds capacity
    assert limiter.try_acquire(tenant, tool) is False


def test_circuit_breaker_transition_and_recovery():
    # Set low threshold and short recovery timeout for testing
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout_seconds=0.1)
    tenant = "t1"
    tool = "unstable_service"

    assert cb.state(tenant, tool) == "closed"
    assert cb.can_execute(tenant, tool) is True

    # 1st failure: remains closed
    cb.record_failure(tenant, tool)
    assert cb.state(tenant, tool) == "closed"
    assert cb.can_execute(tenant, tool) is True

    # 2nd failure: trips open
    cb.record_failure(tenant, tool)
    assert cb.state(tenant, tool) == "open"
    assert cb.can_execute(tenant, tool) is False

    # Wait for recovery timeout
    time.sleep(0.12)
    assert cb.state(tenant, tool) == "half-open"
    # First flight is allowed
    assert cb.can_execute(tenant, tool) is True
    # Second flight while trial is in progress is blocked
    assert cb.can_execute(tenant, tool) is False

    # Trial succeeds -> closed
    cb.record_success(tenant, tool)
    assert cb.state(tenant, tool) == "closed"
    assert cb.can_execute(tenant, tool) is True


@pytest.mark.anyio
async def test_concurrency_limiter():
    limiter = ConcurrencyLimiter(default_limit=2)
    sem = limiter.get_semaphore("tool_x")

    assert sem._value == 2
    async with sem:
        assert sem._value == 1
    assert sem._value == 2
