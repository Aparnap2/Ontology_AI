"""SLA clock engine + Temporal waiting (Phase 5).

Deterministic deadline math, state machine, escalation ladder, race
semantics, and the Temporal workflow shape. All clocks inject `now`;
nothing reads wall-clock, nothing polls, no LLM involved.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.entities.models import EscalationPolicy, SLA
from src.mission.sla_clocks import (
    ClockEvent,
    ClockState,
    InMemorySLAWaiter,
    InvalidClockTransitionError,
    UnsupportedCalendarError,
    apply_vendor_response,
    build_phase_waits,
    compute_sla_deadlines,
    deadlines_for_sla,
    describe_wait,
    escalate,
    escalation_signal,
    escalation_target,
    evaluate_at,
    is_met,
    ladder_from_policy,
    open_clock,
    phase_timeout_seconds,
    transition,
)

T0 = datetime(2026, 9, 12, 2, 13, tzinfo=timezone.utc)


def _sla(**over):
    base = dict(
        id="sla-1", tenant_id="t1", name="P1", service_id="svc-pay",
        contract_id="c-1", priority="critical", acknowledgement_minutes=15,
        update_minutes=60, resolution_minutes=240,
        escalation_policy_id="esc-1", business_calendar="24x7", active=True,
    )
    base.update(over)
    return SLA(**base)


def _policy(**over):
    base = dict(
        id="esc-1", tenant_id="t1", name="vendor-escalation",
        t0_vendor_primary="vendor-primary", t1_vendor_escalation="vendor-mgmt",
        t2_internal_owner="it-lead", t3_hitl_material="founder",
        authority={}, requires_hitl=True,
    )
    base.update(over)
    return EscalationPolicy(**base)


def _clock(**over):
    deadlines = compute_sla_deadlines(
        T0, acknowledgement_minutes=15, update_minutes=60, resolution_minutes=240
    )
    clock = open_clock("inc-1", "t1", deadlines, has_update_phase=True)
    clock = transition(clock, ClockEvent.START)
    for key, value in over.items():
        object.__setattr__(clock, key, value)
    return clock


# ── Deadline math ────────────────────────────────────────────────────────


def test_deadlines_from_detected_at():
    d = compute_sla_deadlines(
        T0, acknowledgement_minutes=15, update_minutes=60, resolution_minutes=240
    )
    assert d.ack_deadline == T0 + timedelta(minutes=15)
    assert d.update_deadline == T0 + timedelta(minutes=60)
    assert d.resolution_deadline == T0 + timedelta(hours=4)


def test_deadlines_from_sla_entity():
    d = deadlines_for_sla(_sla(), T0)
    assert d.ack_deadline == T0 + timedelta(minutes=15)


def test_unsupported_calendar_fails_closed():
    with pytest.raises(UnsupportedCalendarError):
        compute_sla_deadlines(
            T0, acknowledgement_minutes=15, update_minutes=None,
            resolution_minutes=60, business_calendar="business-hours",
        )


def test_no_update_phase_skips_update_deadline():
    d = compute_sla_deadlines(
        T0, acknowledgement_minutes=15, update_minutes=None, resolution_minutes=60
    )
    assert d.update_deadline is None


# ── Boundary semantics ───────────────────────────────────────────────────


def test_at_deadline_counts_as_met():
    assert is_met(T0, T0) is True
    assert is_met(T0 - timedelta(seconds=1), T0) is True
    assert is_met(T0 + timedelta(seconds=1), T0) is False


# ── State machine ────────────────────────────────────────────────────────


def test_open_starts_active_then_waiting():
    d = compute_sla_deadlines(
        T0, acknowledgement_minutes=15, update_minutes=None, resolution_minutes=60
    )
    clock = open_clock("i", "t1", d, has_update_phase=False)
    assert clock.state == ClockState.ACTIVE
    assert transition(clock, ClockEvent.START).state == ClockState.WAITING_FOR_ACK


def test_invalid_transitions_raise():
    started = transition(
        open_clock("i", "t1", _clock().deadlines, has_update_phase=True),
        ClockEvent.START,
    )
    with pytest.raises(InvalidClockTransitionError):
        transition(started, ClockEvent.START)  # already started
    with pytest.raises(InvalidClockTransitionError):
        transition(
            open_clock("i", "t1", _clock().deadlines, has_update_phase=True),
            ClockEvent.ACK_RECEIVED,
        )  # never started
    with pytest.raises(InvalidClockTransitionError):
        transition(_clock(), ClockEvent.ESCALATE)  # nothing breached


def test_breach_then_escalate_then_resolve():
    clock = _clock()
    breached = transition(clock, ClockEvent.DEADLINE_PASSED)
    assert breached.state == ClockState.BREACHED
    escalated = escalate(breached, ladder_from_policy(_policy()))
    assert escalated.state == ClockState.ESCALATED
    assert escalated.tier == 1
    assert escalated.escalations[0]["target"] == "vendor-mgmt"


def test_evaluate_at_drives_breach():
    clock = _clock()
    assert evaluate_at(clock, T0 + timedelta(minutes=1)) is None
    assert evaluate_at(clock, T0 + timedelta(minutes=16)) == ClockEvent.DEADLINE_PASSED


# ── Escalation ladder ────────────────────────────────────────────────────


def test_ladder_t0_to_t3_contacts():
    ladder = ladder_from_policy(_policy())
    assert [escalation_target(ladder, t) for t in range(4)] == [
        "vendor-primary", "vendor-mgmt", "it-lead", "founder",
    ]
    with pytest.raises(ValueError):
        escalation_target(ladder, 4)


def test_terminal_tier_raises_hitl_signal():
    ladder = ladder_from_policy(_policy())
    assert escalation_signal(ladder, 3) == "hitl-approval"
    assert escalation_signal(ladder, 1) == "vendor-escalation"


# ── Race semantics ───────────────────────────────────────────────────────


def test_response_before_deadline_accepted():
    clock = apply_vendor_response(
        _clock(), {"kind": "ack", "response_id": "r1"}, at=T0 + timedelta(minutes=14)
    )
    assert clock.state == ClockState.WAITING_FOR_UPDATE


def test_response_exactly_at_deadline_accepted():
    clock = apply_vendor_response(
        _clock(), {"kind": "ack", "response_id": "r1"}, at=T0 + timedelta(minutes=15)
    )
    assert clock.state == ClockState.WAITING_FOR_UPDATE


def test_response_after_deadline_records_breach_first():
    """Late-but-waiting: breach recorded, then the response is accepted."""
    clock = apply_vendor_response(
        _clock(), {"kind": "ack", "response_id": "r1"}, at=T0 + timedelta(minutes=16)
    )
    assert clock.breached_phase == "ack"
    assert clock.last_response_late is True
    assert clock.state == ClockState.WAITING_FOR_UPDATE


def test_duplicate_response_is_noop():
    clock = apply_vendor_response(
        _clock(), {"kind": "ack", "response_id": "r1"}, at=T0 + timedelta(minutes=1)
    )
    again = apply_vendor_response(
        clock, {"kind": "ack", "response_id": "r1"}, at=T0 + timedelta(minutes=2)
    )
    assert again == clock


def test_late_response_after_escalation_accepted_keeps_history():
    clock = _clock()
    clock = transition(clock, ClockEvent.DEADLINE_PASSED)
    clock = escalate(clock, ladder_from_policy(_policy()))
    late = apply_vendor_response(
        clock, {"kind": "ack", "response_id": "r9"}, at=T0 + timedelta(hours=2)
    )
    assert late.last_response_late is True
    assert late.escalations == clock.escalations


def test_unknown_response_kind_rejected():
    with pytest.raises(InvalidClockTransitionError):
        apply_vendor_response(_clock(), {"kind": "telepathy"}, at=T0)


# ── Waiter mirror ────────────────────────────────────────────────────────


def test_waiter_implements_signal_handler_protocol():
    from src.mission.signal_handler import SignalHandler

    assert isinstance(InMemorySLAWaiter(), SignalHandler)


async def test_waiter_emit_await_resolve():
    waiter = InMemorySLAWaiter()
    waiter.emit("sla-vendor-response", {"phase": "ack"})
    import asyncio

    task = asyncio.create_task(waiter.await_decision("sla-vendor-response"))
    await asyncio.sleep(0)
    waiter.resolve({"kind": "ack", "response_id": "r1"})
    assert (await task)["kind"] == "ack"


# ── Wait description / timeouts ──────────────────────────────────────────


def test_describe_wait_per_state():
    assert describe_wait(_clock()).phase == "ack"
    assert describe_wait(_clock()).deadline == T0 + timedelta(minutes=15)
    escalated = escalate(
        transition(_clock(), ClockEvent.DEADLINE_PASSED),
        ladder_from_policy(_policy()),
    )
    waiting = describe_wait(escalated)
    assert waiting is not None and waiting.deadline is None  # signal-only, no timer
    resolved_clock = _clock()
    object.__setattr__(resolved_clock, "state", ClockState.RESOLVED)
    assert describe_wait(resolved_clock) is None


def test_phase_timeout_seconds_floored():
    assert phase_timeout_seconds(T0 + timedelta(minutes=5), T0) == 300.0
    assert phase_timeout_seconds(T0 - timedelta(minutes=5), T0) == 0.0


def test_build_phase_waits_ordered():
    d = compute_sla_deadlines(
        T0, acknowledgement_minutes=15, update_minutes=60, resolution_minutes=240
    )
    waits = build_phase_waits(d, has_update_phase=True)
    assert [w.phase for w in waits] == ["ack", "update", "resolution"]
    assert [w.phase for w in build_phase_waits(d, has_update_phase=False)] == [
        "ack", "resolution",
    ]


# ── Structural guards ────────────────────────────────────────────────────


def test_no_polling_or_wall_clock_in_core():
    from pathlib import Path

    for name in ("sla_clocks.py",):
        src = (Path(__file__).resolve().parent.parent / "src" / "mission" / name).read_text()
        assert "time.sleep" not in src
        assert "datetime.now(" not in src
        assert "while True" not in src


def test_workflow_delegates_decisions_to_core():
    import src.workflows.sla_clock_workflow as wf_mod
    from pathlib import Path

    src = Path(wf_mod.__file__).read_text()
    assert "wait_condition" in src  # durable timer, not polling
    assert "apply_vendor_response" in src
    assert "compute_sla_deadlines" in src or "deadlines_for_sla" in src
    assert "datetime.now(" not in src
