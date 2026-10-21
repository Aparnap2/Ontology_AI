"""Hero Demo Tests — proves the complete 02:13 vendor incident flow.

Tests that the hero demo module:
1. Runs to completion (all 10 timeline events recorded)
2. All timeline events are recorded in order
3. Audit trail is complete (every step has an event)
4. ROI calculation produces positive savings
5. All models strict (extra=forbid rejects unknown fields)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.mission.hero_demo import (
    DEMO_INCIDENT_ID,
    DEMO_TENANT,
    DEMO_VENDOR_ID,
    AuditTrailEvent,
    DemoEventType,
    DemoResult,
    InMemoryVendorTicketStore,
    ingest_incident_event,
    run_hero_demo,
)
from src.mission.recovery_verification import (
    RecoveryPredicate,
    verify_recovery,
)
from src.mission.roi_measurement import (
    ROIMetrics,
    ROISavings,
    calculate_roi,
)


# ── Helper: deterministic clock ──────────────────────────────────────────

T0 = datetime(2026, 9, 12, 2, 13, tzinfo=timezone.utc)


def _fixed_now():
    """Return a fixed timestamp for deterministic testing."""
    return T0 + timedelta(minutes=5)


# ── Test 1: Demo runs to completion ──────────────────────────────────────


@pytest.mark.asyncio
async def test_hero_demo_runs_to_completion():
    """The demo completes all 10 steps without error."""
    result = await run_hero_demo(now_fn=_fixed_now)

    assert isinstance(result, DemoResult)
    assert len(result.timeline_events) == 11  # 10 steps + DEMO_COMPLETED

    # Verify all expected event types appear
    expected = [e.value for e in DemoEventType]
    assert result.timeline_events == expected


# ── Test 2: All timeline events are recorded in order ────────────────────


@pytest.mark.asyncio
async def test_hero_demo_timeline_events_recorded_in_order():
    """Every timeline event is recorded and in the correct sequence."""
    result = await run_hero_demo(now_fn=_fixed_now)

    expected_order = [
        DemoEventType.INCIDENT_INGESTED,
        DemoEventType.SITUATION_OPENED,
        DemoEventType.INVESTIGATION_STARTED,
        DemoEventType.INVESTIGATION_COMPLETED,
        DemoEventType.VENDOR_TICKET_SUBMITTED,
        DemoEventType.VENDOR_TICKET_VERIFIED,
        DemoEventType.SLA_CLOCK_OPENED,
        DemoEventType.RECOVERY_ATTEMPTED_FALSE,
        DemoEventType.VENDOR_CLAIMED_FIXED,
        DemoEventType.RECOVERY_VERIFIED_TRUE,
        DemoEventType.DEMO_COMPLETED,
    ]
    for i, event_type in enumerate(expected_order):
        assert result.audit_trail[i]["event_type"] == event_type.value


# ── Test 3: Audit trail is complete ──────────────────────────────────────


@pytest.mark.asyncio
async def test_hero_demo_audit_trail_complete():
    """Every step in the demo has a corresponding audit trail event."""
    result = await run_hero_demo(now_fn=_fixed_now)

    # 11 events total
    assert len(result.audit_trail) == 11

    # Every event has required fields
    for event in result.audit_trail:
        assert "event_type" in event
        assert "timestamp" in event
        assert "details" in event

    # Evidence ingested
    ev = result.audit_trail[0]
    assert ev["event_type"] == "INCIDENT_INGESTED"
    assert ev["details"]["evidence_id"] == f"ev-{DEMO_INCIDENT_ID}"
    assert ev["details"]["vendor_id"] == DEMO_VENDOR_ID

    # Situation opened
    sit = result.audit_trail[1]
    assert sit["event_type"] == "SITUATION_OPENED"
    assert sit["details"]["situation_type"] == "VENDOR_INCIDENT"
    assert sit["details"]["severity"] == "critical"

    # Vendor ticket created and verified
    ticket_events = [e for e in result.audit_trail if "TICKET" in e["event_type"]]
    assert len(ticket_events) == 2
    assert ticket_events[0]["event_type"] == "VENDOR_TICKET_SUBMITTED"
    assert ticket_events[1]["event_type"] == "VENDOR_TICKET_VERIFIED"

    # SLA clock opened
    sla_event = result.audit_trail[6]
    assert sla_event["event_type"] == "SLA_CLOCK_OPENED"
    assert sla_event["details"]["state"] == "WAITING_FOR_ACK"

    # False recovery attempt
    false_recovery = result.audit_trail[7]
    assert false_recovery["event_type"] == "RECOVERY_ATTEMPTED_FALSE"
    assert false_recovery["details"]["verified"] is False
    assert len(false_recovery["details"]["mismatches"]) > 0

    # True recovery verified
    true_recovery = result.audit_trail[9]
    assert true_recovery["event_type"] == "RECOVERY_VERIFIED_TRUE"
    assert true_recovery["details"]["verified"] is True

    # Demo completed
    complete = result.audit_trail[10]
    assert complete["event_type"] == "DEMO_COMPLETED"
    assert complete["details"]["final_sla_state"] == "RESOLVED"


# ── Test 4: ROI calculation produces positive savings ────────────────────


def test_roi_positive_savings():
    """Governed response is faster and cheaper than manual baseline."""
    baseline = ROIMetrics(
        time_to_detect_minutes=30.0,
        time_to_acknowledge_minutes=45.0,
        time_to_resolve_minutes=240.0,
        sla_compliance=False,
        escalation_count=5,
        vendor_ticket_created=True,
        recovery_verified=False,
        total_cost_usd=12000.0,
    )
    governed = ROIMetrics(
        time_to_detect_minutes=2.0,
        time_to_acknowledge_minutes=10.0,
        time_to_resolve_minutes=45.0,
        sla_compliance=True,
        escalation_count=1,
        vendor_ticket_created=True,
        recovery_verified=True,
        total_cost_usd=2250.0,
    )

    savings = calculate_roi(governed, baseline)

    assert isinstance(savings, ROISavings)
    assert savings.total_savings_usd > 0
    assert savings.time_saved_detect_minutes == 28.0
    assert savings.time_saved_acknowledge_minutes == 35.0
    assert savings.time_saved_resolve_minutes == 195.0
    assert savings.escalation_reduction == 4
    assert savings.sla_met_improvement is True
    assert savings.recovery_verified_improvement is True


def test_roi_zero_savings_when_baseline_equals_governed():
    """No savings when baseline and governed are identical."""
    metrics = ROIMetrics(
        time_to_detect_minutes=10.0,
        time_to_acknowledge_minutes=10.0,
        time_to_resolve_minutes=60.0,
        sla_compliance=True,
        escalation_count=1,
        vendor_ticket_created=True,
        recovery_verified=True,
        total_cost_usd=3000.0,
    )
    savings = calculate_roi(metrics, metrics)
    assert savings.total_savings_usd == 0.0
    assert savings.time_saved_detect_minutes == 0.0
    assert savings.escalation_reduction == 0
    assert savings.sla_met_improvement is False


def test_roi_cost_saved_formula():
    """Cost savings = (resolve time saved × downtime cost) + (escalations reduced × escalation cost)."""
    baseline = ROIMetrics(
        time_to_detect_minutes=5.0,
        time_to_acknowledge_minutes=5.0,
        time_to_resolve_minutes=100.0,
        sla_compliance=False,
        escalation_count=3,
        vendor_ticket_created=False,
        recovery_verified=False,
        total_cost_usd=5000.0,
    )
    governed = ROIMetrics(
        time_to_detect_minutes=1.0,
        time_to_acknowledge_minutes=1.0,
        time_to_resolve_minutes=40.0,
        sla_compliance=True,
        escalation_count=1,
        vendor_ticket_created=True,
        recovery_verified=True,
        total_cost_usd=2000.0,
    )

    savings = calculate_roi(
        governed,
        baseline,
        downtime_cost_per_minute=100.0,
        escalation_cost_usd=500.0,
    )
    # resolve time saved = 100 - 40 = 60 minutes → $6000
    # escalations reduced = 3 - 1 = 2 → $1000
    assert savings.cost_saved_usd == 6000.0
    assert savings.total_savings_usd == 7000.0


# ── Test 5: All models strict (extra=forbid) ────────────────────────────


def test_roi_metrics_rejects_extra_fields():
    """ROIMetrics rejects unknown fields (extra=forbid, strict=True)."""
    with pytest.raises(Exception):  # ValidationError
        ROIMetrics(
            time_to_detect_minutes=5.0,
            time_to_acknowledge_minutes=5.0,
            time_to_resolve_minutes=60.0,
            sla_compliance=True,
            escalation_count=1,
            vendor_ticket_created=True,
            recovery_verified=True,
            total_cost_usd=3000.0,
            sneaky_field="not allowed",  # type: ignore
        )


def test_roi_savings_rejects_extra_fields():
    """ROISavings rejects unknown fields."""
    with pytest.raises(Exception):
        ROISavings(
            time_saved_detect_minutes=0.0,
            time_saved_acknowledge_minutes=0.0,
            time_saved_resolve_minutes=0.0,
            escalation_reduction=0,
            cost_saved_usd=0.0,
            sla_met_improvement=False,
            recovery_verified_improvement=False,
            total_savings_usd=0.0,
            sneaky_field="not allowed",  # type: ignore
        )


def test_demo_result_rejects_extra_fields():
    """DemoResult rejects unknown fields."""
    with pytest.raises(Exception):
        DemoResult(
            evidence={},
            situation={},
            investigation_output={},
            vendor_ticket={},
            sla_clock={},
            false_recovery_outcome={},
            final_recovery_outcome={},
            sneaky_field="not allowed",  # type: ignore
        )


def test_audit_trail_event_rejects_extra_fields():
    """AuditTrailEvent rejects unknown fields."""
    with pytest.raises(Exception):
        AuditTrailEvent(
            event_type="TEST",
            timestamp="2026-01-01T00:00:00Z",
            sneaky_field="not allowed",  # type: ignore
        )


# ── Test 6: Ingest event produces correct Evidence ──────────────────────


def test_ingest_incident_event_produces_correct_evidence():
    """Ingesting an event creates Evidence with correct attribution."""
    event = {
        "incident_id": "inc-test-1",
        "tenant_id": "t-test",
        "title": "Test incident",
        "description": "Something broke",
        "vendor_id": "stripe",
        "severity": "high",
        "detected_at": "2026-09-12T02:13:00Z",
        "source": "monitoring",
        "reporter": "ops-bot",
    }
    evidence = ingest_incident_event(event)

    assert evidence.id == "ev-inc-test-1"
    assert evidence.tenant_id == "t-test"
    assert evidence.source == "monitoring"
    assert evidence.provenance == "incident:stripe:ops-bot"
    assert evidence.raw_text == "Something broke"
    assert "[incident report by ops-bot via monitoring]" in evidence.normalized_text


# ── Test 7: InMemoryVendorTicketStore round-trip ────────────────────────


def test_vendor_ticket_store_round_trip():
    """Create and retrieve a ticket from the in-memory store."""
    store = InMemoryVendorTicketStore()
    params = {
        "vendor_id": "stripe",
        "incident_id": "inc-1",
        "title": "Test ticket",
        "status": "open",
    }
    ticket = store.create(params)
    assert ticket["ticket_id"] == "vt-inc-1"

    retrieved = store.get(ticket["ticket_id"])
    assert retrieved is not None
    assert retrieved["vendor_id"] == "stripe"
    assert retrieved["status"] == "open"

    assert store.get("nonexistent") is None


# ── Test 8: Recovery predicates — false and true recovery ───────────────


def test_recovery_predicates_false_recovery():
    """Predicates fail when error rate is too high."""
    predicates = [
        RecoveryPredicate(field="error_rate", op="lt", threshold=0.01),
        RecoveryPredicate(field="success_rate", op="gte", threshold=0.99),
    ]
    observed = {"error_rate": 0.35, "success_rate": 0.65}
    outcome = verify_recovery(
        incident={"id": "inc-1"}, predicates=predicates, observed=observed
    )
    assert outcome.verified is False
    assert "error_rate" in outcome.mismatches
    assert "success_rate" in outcome.mismatches


def test_recovery_predicates_true_recovery():
    """Predicates pass when error rate is zero."""
    predicates = [
        RecoveryPredicate(field="error_rate", op="lt", threshold=0.01),
        RecoveryPredicate(field="success_rate", op="gte", threshold=0.99),
    ]
    observed = {"error_rate": 0.0, "success_rate": 1.0}
    outcome = verify_recovery(
        incident={"id": "inc-1"}, predicates=predicates, observed=observed
    )
    assert outcome.verified is True
    assert outcome.passed == ["error_rate", "success_rate"]
    assert outcome.mismatches == []


# ── Test 9: SLA clock lifecycle in demo ──────────────────────────────────


@pytest.mark.asyncio
async def test_hero_demo_sla_clock_lifecycle():
    """The SLA clock transitions through the expected states."""
    result = await run_hero_demo(now_fn=_fixed_now)

    sla = result.sla_clock
    assert sla["incident_id"] == DEMO_INCIDENT_ID
    assert sla["tenant_id"] == DEMO_TENANT
    assert sla["state"] == "RESOLVED"
    assert sla["has_update_phase"] is True
    assert sla["tier"] == 0  # no escalation needed


# ── Test 10: Vendor ticket is created and verified ──────────────────────


@pytest.mark.asyncio
async def test_hero_demo_vendor_ticket_created():
    """A vendor ticket is created, verified, and stored."""
    result = await run_hero_demo(now_fn=_fixed_now)

    ticket = result.vendor_ticket
    assert ticket["ticket_id"] == f"vt-{DEMO_INCIDENT_ID}"
    assert ticket["vendor_id"] == DEMO_VENDOR_ID
    assert ticket["incident_id"] == DEMO_INCIDENT_ID
    assert ticket["status"] == "open"
