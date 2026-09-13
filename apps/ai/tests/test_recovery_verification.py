"""Phase 7: Recovery Verification — reject false recovery.

Vendor "fixed" ≠ recovered.  Recovery is predicate-based: every predicate
must pass against observed system state.  A vendor claiming resolution
while monitoring still shows errors is rejected.  Empty predicates fail
closed (never silent pass).

Test-first (RED): every assertion encodes a business requirement before
any implementation exists.
"""
from __future__ import annotations

from datetime import datetime, timezone


# ── SUT under test (does not exist yet — RED) ────────────────────────────

from src.mission.recovery_verification import (
    RecoveryPredicate,
    evaluate_predicates,
    verify_recovery,
)


T0 = datetime(2026, 9, 12, 14, 30, tzinfo=timezone.utc)


# ── Helpers ──────────────────────────────────────────────────────────────


def _incident(**over):
    base = dict(
        id="inc-1",
        tenant_id="t1",
        title="Payment gateway 503",
        service_id="svc-pay",
        vendor_id="stripe",
        status="open",
    )
    base.update(over)
    return base


def _observed(**over):
    """Simulated observed system state (what monitoring sees, not what vendor claims)."""
    base = dict(
        error_rate=0.0,
        latency_p99_ms=120,
        uptime_pct=99.95,
        incident_count_24h=0,
        vendor_status="resolved",
    )
    base.update(over)
    return base


# ── 1. All predicates pass → verified (actual recovery) ──────────────────


def test_all_predicates_pass_verified():
    predicates = [
        RecoveryPredicate(field="error_rate", op="lt", threshold=0.01),
        RecoveryPredicate(field="latency_p99_ms", op="lt", threshold=500),
    ]
    observed = _observed(error_rate=0.002, latency_p99_ms=120)
    outcome = evaluate_predicates(predicates, observed)
    assert outcome.verified is True
    assert outcome.mismatches == []
    assert outcome.passed == ["error_rate", "latency_p99_ms"]


# ── 2. False recovery rejected ───────────────────────────────────────────


def test_false_recovery_rejected():
    """Vendor claims resolved, but error_rate still above threshold."""
    predicates = [
        RecoveryPredicate(field="error_rate", op="lt", threshold=0.01),
        RecoveryPredicate(field="latency_p99_ms", op="lt", threshold=500),
    ]
    observed = _observed(error_rate=0.15, latency_p99_ms=120)  # error rate high
    outcome = evaluate_predicates(predicates, observed)
    assert outcome.verified is False
    assert "error_rate" in outcome.mismatches
    assert outcome.passed == ["latency_p99_ms"]


# ── 3. Partial predicates fail → not verified ────────────────────────────


def test_partial_predicates_fail_not_verified():
    predicates = [
        RecoveryPredicate(field="error_rate", op="lt", threshold=0.01),
        RecoveryPredicate(field="uptime_pct", op="gte", threshold=99.9),
    ]
    observed = _observed(error_rate=0.001, uptime_pct=99.5)  # uptime low
    outcome = evaluate_predicates(predicates, observed)
    assert outcome.verified is False
    assert "uptime_pct" in outcome.mismatches


# ── 4. Empty predicates fail closed ──────────────────────────────────────


def test_empty_predicates_fail_closed():
    observed = _observed()
    outcome = evaluate_predicates([], observed)
    assert outcome.verified is False
    assert outcome.mismatches == ["no_predicates"]


# ── 5. Operator semantics ───────────────────────────────────────────────


def test_operators():
    predicates = [
        RecoveryPredicate(field="error_rate", op="lte", threshold=0.0),
        RecoveryPredicate(field="latency_p99_ms", op="gt", threshold=0),
        RecoveryPredicate(field="uptime_pct", op="eq", threshold=99.95),
        RecoveryPredicate(field="incident_count_24h", op="neq", threshold=5),
    ]
    observed = _observed(error_rate=0.0, latency_p99_ms=120, uptime_pct=99.95, incident_count_24h=0)
    outcome = evaluate_predicates(predicates, observed)
    assert outcome.verified is True


def test_unknown_operator_fails_closed():
    predicates = [RecoveryPredicate(field="error_rate", op="within_band", threshold=0.01)]
    outcome = evaluate_predicates(predicates, _observed())
    assert outcome.verified is False
    assert "unknown_op:within_band" in outcome.mismatches


# ── 6. Predicate with missing observed field ─────────────────────────────


def test_missing_observed_field_fails_closed():
    predicates = [RecoveryPredicate(field="nonexistent_field", op="lt", threshold=1)]
    outcome = evaluate_predicates(predicates, _observed())
    assert outcome.verified is False
    assert "missing:nonexistent_field" in outcome.mismatches


# ── 7. verify_recovery integration ──────────────────────────────────────


def test_verify_recovery_happy_path():
    incident = _incident(status="open")
    predicates = [RecoveryPredicate(field="error_rate", op="lt", threshold=0.01)]
    observed = _observed(error_rate=0.001)
    outcome = verify_recovery(incident, predicates, observed)
    assert outcome.verified is True


def test_verify_recovery_false_claim_rejected():
    """Vendor set status=resolved, but predicates disagree → rejected."""
    incident = _incident(status="closed")  # vendor already marked closed
    predicates = [RecoveryPredicate(field="error_rate", op="lt", threshold=0.01)]
    observed = _observed(error_rate=0.20)  # monitoring says errors still high
    outcome = verify_recovery(incident, predicates, observed)
    assert outcome.verified is False
    assert outcome.incident_id == "inc-1"


# ── 8. Structural: no I/O, no LLM, no wall clock ───────────────────────


def test_no_io_or_llm_in_recovery_module():
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "src" / "mission" / "recovery_verification.py"
    text = src.read_text()
    assert "time.sleep" not in text
    assert "datetime.now(" not in text
    assert "while True" not in text
    assert "import openai" not in text
    assert "chat_completion" not in text
