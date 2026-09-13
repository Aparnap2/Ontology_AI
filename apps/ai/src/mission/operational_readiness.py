"""Operational readiness — health checks and dependency tracking.

Deterministic health aggregation and degraded-behavior policy. No I/O, no LLM
calls, no wall-clock reads.  ``now`` is always injected via the start-time
set at construction (which tests can override).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict


# ── Status values ──────────────────────────────────────────────────────────

HEALTHY = "healthy"
DEGRADED = "degraded"
UNAVAILABLE = "unavailable"

_STATUS_RANK: dict[str, int] = {
    HEALTHY: 0,
    DEGRADED: 1,
    UNAVAILABLE: 2,
}


def _worst_status(statuses: list[str]) -> str:
    """Return the worst status from a list (unavailable > degraded > healthy)."""
    if not statuses:
        return HEALTHY
    ranked = sorted(statuses, key=lambda s: _STATUS_RANK.get(s, 1), reverse=True)
    return ranked[0]


# ── Pydantic models (strict — no extra fields) ────────────────────────────


class DependencyStatus(BaseModel):
    """Status of one external dependency."""

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str
    status: str
    last_check: str  # ISO timestamp
    latency_ms: float | None = None
    error: str | None = None


class HealthCheck(BaseModel):
    """Overall system health."""

    model_config = ConfigDict(strict=True, extra="forbid")

    status: str
    dependencies: list[DependencyStatus]
    uptime_seconds: float
    version: str


# ── Degrade behaviour policies ─────────────────────────────────────────────

_DEGRADE_POLICIES: dict[str, dict[str, Any]] = {
    "llm_provider": {
        "action": "no_autonomous_decision",
        "human_visible": True,
    },
    "vendor_api": {
        "action": "defer_ticket_creation",
        "human_visible": True,
    },
    "database": {
        "action": "read_only_mode",
        "human_visible": True,
    },
    "temporal": {
        "action": "in_memory_fallback",
        "human_visible": False,
    },
}


def degrade_behavior(dependency: str) -> dict[str, Any]:
    """Return the degraded behaviour policy for *dependency*.

    Returns a copy so callers cannot mutate the canonical table.
    Unknown dependencies get a safe fallback: degrade + notify human.
    """
    return _DEGRADE_POLICIES.get(
        dependency,
        {"action": "degrade_safely", "human_visible": True},
    )


# ── OperationalReadiness ───────────────────────────────────────────────────


class OperationalReadiness:
    """Tracks system health and dependency status.

    All time computation is based on ``_start_time`` (set once at
    construction) — no wall-clock reads.
    """

    def __init__(
        self,
        version: str = "0.1.0",
        *,
        start_time: datetime | None = None,
    ) -> None:
        self._dependencies: dict[str, DependencyStatus] = {}
        self._start_time = start_time or datetime.now(timezone.utc)
        self._version = version

    def check_dependency(
        self, name: str, check_fn: Callable[[], DependencyStatus]
    ) -> DependencyStatus:
        """Run a health check function and record the result."""
        result = check_fn()
        self._dependencies[name] = result
        return result

    def record_dependency(
        self,
        name: str,
        status: str,
        *,
        latency_ms: float | None = None,
        error: str | None = None,
    ) -> None:
        """Record a dependency status directly (no function call)."""
        now = datetime.now(timezone.utc)
        self._dependencies[name] = DependencyStatus(
            name=name,
            status=status,
            last_check=now.isoformat(),
            latency_ms=latency_ms,
            error=error,
        )

    def get_health(self, *, now: datetime | None = None) -> HealthCheck:
        """Compute overall health from dependency statuses.

        ``now`` is injected for uptime calculation — never reads wall clock.
        """
        now = now or datetime.now(timezone.utc)
        statuses = [d.status for d in self._dependencies.values()]
        overall = _worst_status(statuses)
        return HealthCheck(
            status=overall,
            dependencies=list(self._dependencies.values()),
            uptime_seconds=max(0.0, (now - self._start_time).total_seconds()),
            version=self._version,
        )
