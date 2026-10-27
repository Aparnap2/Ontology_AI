"""Operational readiness — health checks and degraded-behaviour policy.

No I/O, no LLM, no wall-clock.  All time is injected via ``start_time``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from src.mission.operational_readiness import (
    DependencyStatus,
    HealthCheck,
    OperationalReadiness,
    degrade_behavior,
)


T0 = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)


# ── Helpers ────────────────────────────────────────────────────────────────


def _dep(name: str, status: str, **kw: Any) -> DependencyStatus:
    """Build a DependencyStatus with defaults."""
    defaults: dict[str, Any] = {
        "name": name,
        "status": status,
        "last_check": "2026-09-13T10:00:00+00:00",
        "latency_ms": None,
        "error": None,
    }
    defaults.update(kw)
    return DependencyStatus(**defaults)


def _ready(*, version: str = "1.0.0", start: datetime = T0) -> OperationalReadiness:
    return OperationalReadiness(version=version, start_time=start)


# ── 1. Health check reflects dependency statuses ──────────────────────────


def test_health_check_reflects_recorded_dependencies() -> None:
    orr = _ready()
    orr.record_dependency("database", "healthy", latency_ms=12.0)
    orr.record_dependency("temporal", "degraded", error="slow heartbeat")

    health = orr.get_health(now=T0)
    assert len(health.dependencies) == 2
    names = {d.name for d in health.dependencies}
    assert names == {"database", "temporal"}


def test_check_dependency_runs_function() -> None:
    orr = _ready()

    def check_db() -> DependencyStatus:
        return _dep("database", "healthy", latency_ms=5.0)

    result = orr.check_dependency("database", check_db)
    assert result.status == "healthy"
    assert result.latency_ms == 5.0
    health = orr.get_health(now=T0)
    assert health.dependencies[0].name == "database"


# ── 2. All healthy → status "healthy" ─────────────────────────────────────


def test_all_healthy_gives_healthy() -> None:
    orr = _ready()
    orr.record_dependency("database", "healthy")
    orr.record_dependency("temporal", "healthy")
    orr.record_dependency("llm_provider", "healthy")

    assert orr.get_health(now=T0).status == "healthy"


# ── 3. One degraded → status "degraded" ───────────────────────────────────


def test_one_degraded_gives_degraded() -> None:
    orr = _ready()
    orr.record_dependency("database", "healthy")
    orr.record_dependency("temporal", "degraded")

    assert orr.get_health(now=T0).status == "degraded"


# ── 4. One unavailable → status "unavailable" ─────────────────────────────


def test_one_unavailable_gives_unavailable() -> None:
    orr = _ready()
    orr.record_dependency("database", "healthy")
    orr.record_dependency("llm_provider", "unavailable", error="403 quota exceeded")

    assert orr.get_health(now=T0).status == "unavailable"


# ── 5. Degrade behaviour for each dependency type ─────────────────────────


def test_degrade_behavior_llm_provider() -> None:
    policy = degrade_behavior("llm_provider")
    assert policy["action"] == "no_autonomous_decision"
    assert policy["human_visible"] is True


def test_degrade_behavior_vendor_api() -> None:
    policy = degrade_behavior("vendor_api")
    assert policy["action"] == "defer_ticket_creation"
    assert policy["human_visible"] is True


def test_degrade_behavior_database() -> None:
    policy = degrade_behavior("database")
    assert policy["action"] == "read_only_mode"
    assert policy["human_visible"] is True


def test_degrade_behavior_temporal() -> None:
    policy = degrade_behavior("temporal")
    assert policy["action"] == "in_memory_fallback"
    assert policy["human_visible"] is False


def test_degrade_behavior_unknown_dependency() -> None:
    policy = degrade_behavior("unknown_thing")
    assert policy["human_visible"] is True
    assert isinstance(policy["action"], str)


# ── 6. LLM unavailable → no autonomous decision (key property) ───────────


def test_llm_unavailable_means_no_autonomous_decision() -> None:
    """Proving: when LLM is down, the system MUST NOT make autonomous decisions."""
    policy = degrade_behavior("llm_provider")
    assert policy["action"] == "no_autonomous_decision"
    assert policy["human_visible"] is True

    # Verify it propagates through OperationalReadiness
    orr = _ready()
    orr.record_dependency("llm_provider", "unavailable")
    health = orr.get_health(now=T0)
    assert health.status == "unavailable"


# ── 7. Vendor unavailable → deferred, not failed ──────────────────────────


def test_vendor_unavailable_is_deferred_not_failed() -> None:
    """Proving: vendor outage defers work, does not hard-fail the pipeline."""
    policy = degrade_behavior("vendor_api")
    assert policy["action"] == "defer_ticket_creation"
    assert policy["human_visible"] is True
    # Key invariant: action is "defer", not "abort" or "fail"
    assert "defer" in policy["action"]


# ── 8. Multiple failures → worst status wins ──────────────────────────────


def test_worst_status_wins_with_multiple_failures() -> None:
    orr = _ready()
    orr.record_dependency("database", "degraded")
    orr.record_dependency("temporal", "unavailable")
    orr.record_dependency("llm_provider", "healthy")

    assert orr.get_health(now=T0).status == "unavailable"


def test_all_degraded_stays_degraded() -> None:
    orr = _ready()
    orr.record_dependency("database", "degraded")
    orr.record_dependency("temporal", "degraded")

    assert orr.get_health(now=T0).status == "degraded"


def test_no_dependencies_is_healthy() -> None:
    orr = _ready()
    health = orr.get_health(now=T0)
    assert health.status == "healthy"
    assert health.dependencies == []


# ── 9. All models strict (extra=forbid) ───────────────────────────────────


def test_dependency_status_rejects_extra_fields() -> None:
    with pytest.raises(Exception):
        DependencyStatus(  # type: ignore[call-arg]
            name="db", status="healthy", last_check="x", sneaky="bad"
        )


def test_health_check_rejects_extra_fields() -> None:
    with pytest.raises(Exception):
        HealthCheck(  # type: ignore[call-arg]
            status="healthy",
            dependencies=[],
            uptime_seconds=0.0,
            version="1.0",
            bogus="nope",
        )


# ── 10. No I/O, no LLM, no wall clock ────────────────────────────────────


def test_no_io_no_llm_no_wall_clock_in_source() -> None:
    """Structural guard: the module never reads wall-clock or makes I/O calls."""
    src = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "mission"
        / "operational_readiness.py"
    ).read_text()
    assert "time.sleep" not in src
    assert "while True" not in src
    assert "httpx" not in src
    assert "openai" not in src


# ── Uptime calculation ────────────────────────────────────────────────────


def test_uptime_is_computed_from_start_time() -> None:
    start = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    later = datetime(2026, 9, 13, 11, 30, tzinfo=timezone.utc)
    orr = _ready(start=start)

    health = orr.get_health(now=later)
    assert health.uptime_seconds == 5400.0  # 90 minutes


def test_uptime_never_negative() -> None:
    """If now < start (shouldn't happen, but guard), uptime floors at 0."""
    future = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    past = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    orr = _ready(start=future)

    health = orr.get_health(now=past)
    assert health.uptime_seconds == 0.0


# ── Version propagation ───────────────────────────────────────────────────


def test_version_appears_in_health_check() -> None:
    orr = _ready(version="42.0.0-beta")
    health = orr.get_health(now=T0)
    assert health.version == "42.0.0-beta"
