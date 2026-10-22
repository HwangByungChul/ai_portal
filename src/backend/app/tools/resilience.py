"""Resilience primitives for MCP Tool Gateway: RateLimiter and CircuitBreaker.

Enforces:
- Token Bucket rate limiting per tool and tenant.
- Circuit breaker state transitions (closed -> open -> half-open -> closed) with recovery timeout.
- Tool concurrency limits via asyncio.Semaphore.
"""
from __future__ import annotations

import asyncio
import time
from typing import Literal

from app.errors import AppError


class TokenBucketRateLimiter:
    """Per-tool, per-tenant token bucket rate limiter."""

    def __init__(self, default_max_tokens: int = 60, default_refill_per_sec: float = 1.0) -> None:
        self.default_max_tokens = default_max_tokens
        self.default_refill_per_sec = default_refill_per_sec
        # key: (tenant_id, tool_id) -> (current_tokens, last_refill_time)
        self._buckets: dict[tuple[str, str], tuple[float, float]] = {}

    def try_acquire(
        self,
        tenant_id: str,
        tool_id: str,
        max_tokens: int | None = None,
        refill_rate: float | None = None,
    ) -> bool:
        capacity = max_tokens or self.default_max_tokens
        rate = refill_rate or self.default_refill_per_sec

        now = time.monotonic()
        key = (tenant_id, tool_id)

        if key not in self._buckets:
            self._buckets[key] = (float(capacity) - 1.0, now)
            return True

        tokens, last_time = self._buckets[key]
        elapsed = now - last_time
        tokens = min(float(capacity), tokens + elapsed * rate)

        if tokens >= 1.0:
            self._buckets[key] = (tokens - 1.0, now)
            return True

        self._buckets[key] = (tokens, now)
        return False


class CircuitBreaker:
    """Circuit breaker with closed, open, and half-open states."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout_seconds: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        # key: (tenant_id, tool_id) -> dict(state, consecutive_failures, last_failure_time, half_open_flight)
        self._circuits: dict[tuple[str, str], dict] = {}

    def _get_entry(self, tenant_id: str, tool_id: str) -> dict:
        key = (tenant_id, tool_id)
        if key not in self._circuits:
            self._circuits[key] = {
                "state": "closed",
                "consecutive_failures": 0,
                "last_failure_time": 0.0,
                "half_open_flight": False,
            }
        return self._circuits[key]

    def state(self, tenant_id: str, tool_id: str) -> Literal["closed", "open", "half-open"]:
        entry = self._get_entry(tenant_id, tool_id)
        current_state = entry["state"]

        if current_state == "open":
            now = time.monotonic()
            if now - entry["last_failure_time"] >= self.recovery_timeout_seconds:
                entry["state"] = "half-open"
                entry["half_open_flight"] = False
                return "half-open"

        return entry["state"]

    def can_execute(self, tenant_id: str, tool_id: str) -> bool:
        """Check if execution is permitted under current circuit state."""
        st = self.state(tenant_id, tool_id)
        if st == "closed":
            return True
        if st == "open":
            return False
        # half-open: allow exactly one trial flight
        entry = self._get_entry(tenant_id, tool_id)
        if not entry["half_open_flight"]:
            entry["half_open_flight"] = True
            return True
        return False

    def record_success(self, tenant_id: str, tool_id: str) -> None:
        entry = self._get_entry(tenant_id, tool_id)
        entry["state"] = "closed"
        entry["consecutive_failures"] = 0
        entry["half_open_flight"] = False

    def record_failure(self, tenant_id: str, tool_id: str) -> None:
        entry = self._get_entry(tenant_id, tool_id)
        now = time.monotonic()
        entry["last_failure_time"] = now
        entry["consecutive_failures"] += 1
        entry["half_open_flight"] = False

        if entry["consecutive_failures"] >= self.failure_threshold or entry["state"] == "half-open":
            entry["state"] = "open"


class ConcurrencyLimiter:
    """Per-tool concurrency limiter using asyncio.Semaphore."""

    def __init__(self, default_limit: int = 5) -> None:
        self.default_limit = default_limit
        self._semaphores: dict[str, asyncio.Semaphore] = {}

    def get_semaphore(self, tool_id: str, limit: int | None = None) -> asyncio.Semaphore:
        if tool_id not in self._semaphores:
            self._semaphores[tool_id] = asyncio.Semaphore(limit or self.default_limit)
        return self._semaphores[tool_id]
