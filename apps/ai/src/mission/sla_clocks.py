"""Phase 5 — Deterministic SLA clock engine (zero LLM involvement).

The LLM must not own time: every deadline, transition, and race verdict in
this module is pure arithmetic over caller-supplied timestamps. ``now`` is
always injected — this module never reads a wall clock.

Contents
--------
1. :func:`compute_sla_deadlines` — incident ``detected_at`` + SLA
   acknowledgement/update/resolution minutes → ack/update/resolution
   deadline instants. Business calendar is honored minimally: ``"24x7"``
   means plain arithmetic; any other value raises
   :class:`UnsupportedCalendarError` (explicit failure, never silent wrong
   math).
2. :class:`SLAClock` + :func:`transition` — tiny deterministic state machine
   over ``(state, event)`` with no I/O::

       ACTIVE → WAITING_FOR_ACK → WAITING_FOR_UPDATE → WAITING_FOR_RESOLUTION
                ↘ (update_minutes=None: ack jumps straight to resolution)
       WAITING_* → BREACHED → ESCALATED → RESOLVED
       WAITING_*/BREACHED/ESCALATED → RESOLVED (direct resolution)

   Boundary semantics (documented, tested): a vendor response stamped
   exactly at the deadline counts as MET (``response_at <= deadline``).
   A response after the deadline is LATE: the clock records the breach and
   still accepts the response (late acceptance), including after escalation.
   Duplicate ``response_id`` values are idempotent no-ops.
3. Escalation ladder T0 vendor-primary → T1 vendor-escalation → T2 internal
   owner → T3 HITL-contractual, driven by :class:`EscalationPolicy` via
   :func:`ladder_from_policy` + :func:`escalation_target`.
4. :func:`describe_wait` + :class:`InMemorySLAWaiter` — the
   signal-handler-compatible wait interface. It mirrors
   :class:`src.mission.signal_handler.SignalHandler` (``emit`` /
   ``await_decision`` / ``resolve``) so the production Temporal binding can
   substitute a real workflow signal without changing callers. Difference
   from :class:`InMemorySignalHandler` (deliberate, tested): resolved
   responses are queued, so a ``resolve`` that lands before any awaiter is
   still delivered instead of dropped.

Temporal binding: :mod:`src.workflows.sla_clock_workflow` (same
``temporalio`` framework as the existing workflows — no new orchestration
framework). The incident wait there is a durable timer
(``wait_condition`` + ``timeout``) raced against the ``sla-vendor-response``
signal wake-up. No polling loop exists anywhere in this phase.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


# ── Errors ────────────────────────────────────────────────────────────────


class UnsupportedCalendarError(ValueError):
    """Raised when ``business_calendar`` is anything other than ``"24x7"``.

    Non-trivial calendars (business hours, holidays, per-tenant shifts) need
    an explicit calendar engine. Failing here is intentional: silently
    applying plain arithmetic to a named calendar would produce wrong
    deadlines.
    """


class InvalidClockTransitionError(ValueError):
    """Raised when an event is not valid for the clock's current state."""


# ── States / events ───────────────────────────────────────────────────────


class ClockState(str, Enum):
    """SLA clock lifecycle states."""

    ACTIVE = "ACTIVE"
    WAITING_FOR_ACK = "WAITING_FOR_ACK"
    WAITING_FOR_UPDATE = "WAITING_FOR_UPDATE"
    WAITING_FOR_RESOLUTION = "WAITING_FOR_RESOLUTION"
    BREACHED = "BREACHED"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"


class ClockEvent(str, Enum):
    """Events that drive the clock state machine."""

    START = "START"
    ACK_RECEIVED = "ACK_RECEIVED"
    UPDATE_RECEIVED = "UPDATE_RECEIVED"
    RESOLVED = "RESOLVED"
    DEADLINE_PASSED = "DEADLINE_PASSED"
    ESCALATE = "ESCALATE"


#: Clock phases — the deadline the clock is currently waiting on.
PHASE_ACK = "ack"
PHASE_UPDATE = "update"
PHASE_RESOLUTION = "resolution"
PHASE_DONE = "done"

#: Signal name the vendor-response event arrives on (Temporal + in-memory).
SLA_VENDOR_RESPONSE_SIGNAL = "sla-vendor-response"

#: Signal emitted for the terminal contractual tier when human approval applies.
HITL_APPROVAL_SIGNAL = "hitl-approval"

#: Signal recorded for vendor-side escalation steps (T0–T2, or T3 w/o HITL).
VENDOR_ESCALATION_SIGNAL = "vendor-escalation"

#: The only business calendar this engine computes. Anything else raises.
SUPPORTED_CALENDAR = "24x7"

_WAITING_STATES = frozenset(
    {
        ClockState.WAITING_FOR_ACK,
        ClockState.WAITING_FOR_UPDATE,
        ClockState.WAITING_FOR_RESOLUTION,
    }
)

# Numeric order of phases for staleness checks (resolution is terminal).
_PHASE_ORDER = {PHASE_ACK: 0, PHASE_UPDATE: 1, PHASE_RESOLUTION: 2}


# ── 1. SLA deadline calculation (pure) ────────────────────────────────────


@dataclass(frozen=True)
class SLADeadlines:
    """Deadline instants derived from ``detected_at`` + SLA minute budgets."""

    ack_deadline: datetime
    update_deadline: datetime | None
    resolution_deadline: datetime

    def deadline_for(self, phase: str) -> datetime | None:
        """Return the deadline for a clock phase (None when phase has none)."""
        if phase == PHASE_ACK:
            return self.ack_deadline
        if phase == PHASE_UPDATE:
            return self.update_deadline
        if phase == PHASE_RESOLUTION:
            return self.resolution_deadline
        return None


def compute_sla_deadlines(
    detected_at: datetime,
    *,
    acknowledgement_minutes: int,
    update_minutes: int | None,
    resolution_minutes: int,
    business_calendar: str = SUPPORTED_CALENDAR,
) -> SLADeadlines:
    """Compute ack/update/resolution deadlines from the detection instant.

    Pure arithmetic — never LLM-computed, never wall-clock. ``update_minutes``
    of ``None`` means the SLA carries no update obligation (the clock then
    skips ``WAITING_FOR_UPDATE``).
    """
    if business_calendar != SUPPORTED_CALENDAR:
        raise UnsupportedCalendarError(
            f"unsupported business_calendar={business_calendar!r}: this engine "
            f"computes plain {SUPPORTED_CALENDAR} arithmetic only; refusing to "
            "guess deadline math for a named calendar."
        )
    return SLADeadlines(
        ack_deadline=detected_at + timedelta(minutes=acknowledgement_minutes),
        update_deadline=(
            detected_at + timedelta(minutes=update_minutes)
            if update_minutes is not None
            else None
        ),
        resolution_deadline=detected_at + timedelta(minutes=resolution_minutes),
    )


def deadlines_for_sla(sla: Any, detected_at: datetime) -> SLADeadlines:
    """Build :class:`SLADeadlines` from an SLA entity (field names reused).

    Reads ``acknowledgement_minutes`` / ``update_minutes`` /
    ``resolution_minutes`` / ``business_calendar`` exactly as defined on
    ``src.entities.models.SLA``. ``sla`` is typed ``Any`` (structural) so the
    Temporal workflow sandbox — which must not import Pydantic models — can
    pass any object carrying those attributes.
    """
    return compute_sla_deadlines(
        detected_at,
        acknowledgement_minutes=sla.acknowledgement_minutes,
        update_minutes=sla.update_minutes,
        resolution_minutes=sla.resolution_minutes,
        business_calendar=sla.business_calendar,
    )


def is_met(response_at: datetime, deadline: datetime) -> bool:
    """True when a response meets its deadline.

    Boundary semantics: **at-deadline counts as met**
    (``response_at <= deadline``). A response is LATE only when strictly
    after the deadline. Tested explicitly in ``test_sla_clocks.py``.
    """
    return response_at <= deadline


# ── Escalation ladder (pure) ──────────────────────────────────────────────


#: Ladder tiers: T0 vendor-primary → T1 vendor-escalation → T2 internal
#: owner → T3 HITL-contractual.
MAX_TIER = 3


@dataclass(frozen=True)
class EscalationLadder:
    """Tier contacts resolved from an :class:`EscalationPolicy`.

    The Temporal workflow carries this plain dataclass (never the Pydantic
    model) so the workflow sandbox stays free of model imports.
    """

    t0_vendor_primary: str
    t1_vendor_escalation: str
    t2_internal_owner: str
    t3_hitl_material: str
    requires_hitl: bool = True


def ladder_from_policy(policy: Any) -> EscalationLadder:
    """Resolve an :class:`EscalationPolicy` to its tier-contact ladder.

    Reads ``t0_vendor_primary`` / ``t1_vendor_escalation`` /
    ``t2_internal_owner`` / ``t3_hitl_material`` / ``requires_hitl`` exactly
    as defined on ``src.entities.models.EscalationPolicy``.
    """
    return EscalationLadder(
        t0_vendor_primary=policy.t0_vendor_primary,
        t1_vendor_escalation=policy.t1_vendor_escalation,
        t2_internal_owner=policy.t2_internal_owner,
        t3_hitl_material=policy.t3_hitl_material,
        requires_hitl=policy.requires_hitl,
    )


def escalation_target(ladder: EscalationLadder, tier: int) -> str:
    """Return the contact owning *tier* (0=T0 … 3=T3)."""
    targets = (
        ladder.t0_vendor_primary,
        ladder.t1_vendor_escalation,
        ladder.t2_internal_owner,
        ladder.t3_hitl_material,
    )
    if not 0 <= tier <= MAX_TIER:
        raise ValueError(f"escalation tier out of range 0..{MAX_TIER}: {tier!r}")
    return targets[tier]


def escalation_signal(ladder: EscalationLadder, tier: int) -> str:
    """Return the signal raised for an escalation to *tier*.

    The terminal contractual tier (T3) raises ``hitl-approval`` when the
    policy requires human approval; every other step raises
    ``vendor-escalation``.
    """
    if tier == MAX_TIER and ladder.requires_hitl:
        return HITL_APPROVAL_SIGNAL
    return VENDOR_ESCALATION_SIGNAL


def can_escalate(tier: int) -> bool:
    """True while a further escalation step exists (T3 is terminal)."""
    return tier < MAX_TIER


# ── 2. Clock state machine (pure) ─────────────────────────────────────────


@dataclass(frozen=True)
class SLAClock:
    """Immutable SLA clock snapshot. All changes go through :func:`transition`."""

    incident_id: str
    tenant_id: str
    state: ClockState
    phase: str
    deadlines: SLADeadlines
    has_update_phase: bool
    tier: int = 0
    breached_phase: str | None = None
    seen_response_ids: frozenset = field(default_factory=frozenset)
    escalations: tuple = field(default_factory=tuple)
    last_response_late: bool | None = None


def open_clock(
    incident_id: str,
    tenant_id: str,
    deadlines: SLADeadlines,
    *,
    has_update_phase: bool,
) -> SLAClock:
    """Open a clock in ``ACTIVE``; ``START`` moves it to ``WAITING_FOR_ACK``."""
    return SLAClock(
        incident_id=incident_id,
        tenant_id=tenant_id,
        state=ClockState.ACTIVE,
        phase=PHASE_ACK,
        deadlines=deadlines,
        has_update_phase=has_update_phase,
    )


def _advance_on_ack(clock: SLAClock) -> SLAClock:
    """Move the clock past acknowledgement (skipping update when absent)."""
    if clock.has_update_phase:
        return clock.__class__(
            incident_id=clock.incident_id,
            tenant_id=clock.tenant_id,
            state=ClockState.WAITING_FOR_UPDATE,
            phase=PHASE_UPDATE,
            deadlines=clock.deadlines,
            has_update_phase=clock.has_update_phase,
            tier=clock.tier,
            breached_phase=clock.breached_phase,
            seen_response_ids=clock.seen_response_ids,
            escalations=clock.escalations,
            last_response_late=clock.last_response_late,
        )
    return clock.__class__(
        incident_id=clock.incident_id,
        tenant_id=clock.tenant_id,
        state=ClockState.WAITING_FOR_RESOLUTION,
        phase=PHASE_RESOLUTION,
        deadlines=clock.deadlines,
        has_update_phase=clock.has_update_phase,
        tier=clock.tier,
        breached_phase=clock.breached_phase,
        seen_response_ids=clock.seen_response_ids,
        escalations=clock.escalations,
        last_response_late=clock.last_response_late,
    )


def transition(
    clock: SLAClock,
    event: ClockEvent,
    *,
    response_id: str | None = None,
    escalation_target_name: str | None = None,
    escalation_signal_name: str | None = None,
) -> SLAClock:
    """Apply ``event`` to ``clock`` and return the new snapshot (no I/O).

    Duplicate ``response_id`` values are idempotent no-ops (the identical
    clock is returned). Anything structurally invalid for the current state
    raises :class:`InvalidClockTransitionError`.
    """
    if event in (
        ClockEvent.ACK_RECEIVED,
        ClockEvent.UPDATE_RECEIVED,
        ClockEvent.RESOLVED,
    ):
        if response_id is not None and response_id in clock.seen_response_ids:
            return clock  # duplicate delivery — safe no-op
        seen = clock.seen_response_ids | (
            {response_id} if response_id is not None else frozenset()
        )
        clock = clock.__class__(
            incident_id=clock.incident_id,
            tenant_id=clock.tenant_id,
            state=clock.state,
            phase=clock.phase,
            deadlines=clock.deadlines,
            has_update_phase=clock.has_update_phase,
            tier=clock.tier,
            breached_phase=clock.breached_phase,
            seen_response_ids=seen,
            escalations=clock.escalations,
            last_response_late=clock.last_response_late,
        )
    else:
        seen = clock.seen_response_ids

    def _replace(**overrides: Any) -> SLAClock:
        base: dict[str, Any] = {
            "incident_id": clock.incident_id,
            "tenant_id": clock.tenant_id,
            "state": clock.state,
            "phase": clock.phase,
            "deadlines": clock.deadlines,
            "has_update_phase": clock.has_update_phase,
            "tier": clock.tier,
            "breached_phase": clock.breached_phase,
            "seen_response_ids": seen,
            "escalations": clock.escalations,
            "last_response_late": clock.last_response_late,
        }
        base.update(overrides)
        return SLAClock(**base)

    state = clock.state

    if event == ClockEvent.START:
        if state != ClockState.ACTIVE:
            raise InvalidClockTransitionError(f"START invalid from {state.value}")
        return _replace(state=ClockState.WAITING_FOR_ACK, phase=PHASE_ACK)

    if event == ClockEvent.ACK_RECEIVED:
        if state == ClockState.WAITING_FOR_ACK or (
            state in (ClockState.BREACHED, ClockState.ESCALATED)
            and clock.phase == PHASE_ACK
        ):
            advanced = _advance_on_ack(_replace())
            return advanced
        raise InvalidClockTransitionError(f"ACK_RECEIVED invalid from {state.value}")

    if event == ClockEvent.UPDATE_RECEIVED:
        if not clock.has_update_phase:
            raise InvalidClockTransitionError(
                "UPDATE_RECEIVED invalid: SLA carries no update obligation"
            )
        if state == ClockState.WAITING_FOR_UPDATE or (
            state in (ClockState.BREACHED, ClockState.ESCALATED)
            and clock.phase == PHASE_UPDATE
        ):
            return _replace(
                state=ClockState.WAITING_FOR_RESOLUTION, phase=PHASE_RESOLUTION
            )
        raise InvalidClockTransitionError(f"UPDATE_RECEIVED invalid from {state.value}")

    if event == ClockEvent.RESOLVED:
        if state in _WAITING_STATES | {ClockState.BREACHED, ClockState.ESCALATED}:
            return _replace(state=ClockState.RESOLVED, phase=PHASE_DONE)
        raise InvalidClockTransitionError(f"RESOLVED invalid from {state.value}")

    if event == ClockEvent.DEADLINE_PASSED:
        if state in _WAITING_STATES:
            return _replace(state=ClockState.BREACHED, breached_phase=clock.phase)
        raise InvalidClockTransitionError(f"DEADLINE_PASSED invalid from {state.value}")

    if event == ClockEvent.ESCALATE:
        if state not in (ClockState.BREACHED, ClockState.ESCALATED):
            raise InvalidClockTransitionError(f"ESCALATE invalid from {state.value}")
        if not can_escalate(clock.tier):
            raise InvalidClockTransitionError(
                "ESCALATE invalid: terminal tier T3 reached — the human owns it"
            )
        record = {
            "tier": clock.tier + 1,
            "target": escalation_target_name,
            "signal": escalation_signal_name,
            "phase": clock.breached_phase or clock.phase,
        }
        return _replace(
            state=ClockState.ESCALATED,
            tier=clock.tier + 1,
            escalations=clock.escalations + (record,),
        )

    raise InvalidClockTransitionError(f"unknown event: {event!r}")


def escalate(clock: SLAClock, ladder: EscalationLadder) -> SLAClock:
    """Escalate one ladder step, recording the tier contact + signal (pure)."""
    new_tier = clock.tier + 1
    return transition(
        clock,
        ClockEvent.ESCALATE,
        escalation_target_name=escalation_target(ladder, new_tier),
        escalation_signal_name=escalation_signal(ladder, new_tier),
    )


def evaluate_at(clock: SLAClock, now: datetime) -> ClockEvent | None:
    """Return ``DEADLINE_PASSED`` when the current wait has expired at ``now``.

    Pure race judge: ``now`` strictly after the phase deadline means breach;
    ``now`` exactly at the deadline is NOT a breach (consistent with
    :func:`is_met` — at-deadline responses are met). Returns ``None`` when
    the clock is not waiting or the deadline has not passed.
    """
    if clock.state not in _WAITING_STATES:
        return None
    deadline = clock.deadlines.deadline_for(clock.phase)
    if deadline is None:
        return None
    return ClockEvent.DEADLINE_PASSED if now > deadline else None


# ── Vendor responses incl. deadline races (pure) ──────────────────────────


_RESPONSE_KIND_TO_EVENT = {
    "ack": ClockEvent.ACK_RECEIVED,
    "update": ClockEvent.UPDATE_RECEIVED,
    "resolution": ClockEvent.RESOLVED,
}


def _phase_index_for_kind(kind: str, has_update_phase: bool) -> int:
    order = [PHASE_ACK]
    if has_update_phase:
        order.append(PHASE_UPDATE)
    order.append(PHASE_RESOLUTION)
    return order.index(
        {  # raises ValueError for unknown kinds (fail closed)
            "ack": PHASE_ACK,
            "update": PHASE_UPDATE,
            "resolution": PHASE_RESOLUTION,
        }[kind]
    )


def _current_phase_index(clock: SLAClock) -> int:
    if clock.phase == PHASE_DONE:
        return len(_PHASE_ORDER)  # past every phase
    order = [PHASE_ACK]
    if clock.has_update_phase:
        order.append(PHASE_UPDATE)
    order.append(PHASE_RESOLUTION)
    return order.index(clock.phase)


def apply_vendor_response(
    clock: SLAClock, response: dict[str, Any], *, at: datetime
) -> SLAClock:
    """Apply a vendor response stamped at the injected instant ``at`` (pure).

    ``response`` carries ``kind`` (``"ack"`` | ``"update"`` | ``"resolution"``)
    and an optional ``response_id`` for dedup. Race semantics:

    * ``at`` at-or-before the kind's deadline → met (accepted, on time).
    * ``at`` after the deadline while still waiting → the breach is recorded
      first (``BREACHED``), then the late response is accepted.
    * ``at`` after the deadline when already ``BREACHED``/``ESCALATED`` →
      late acceptance (tier and escalation history are kept).
    * duplicate ``response_id`` → identical clock (no-op), even on RESOLVED.
    * stale kind (phase already passed) → no-op. Responses for a future
      phase other than ``resolution`` raise (out-of-order).

    The vendor's own timestamp never decides the race — only the injected
    ``at`` does. Neither the LLM nor the vendor owns time.
    """
    kind = response.get("kind")
    if kind not in _RESPONSE_KIND_TO_EVENT:
        raise InvalidClockTransitionError(f"unknown vendor response kind: {kind!r}")
    response_id = response.get("response_id")

    if response_id is not None and response_id in clock.seen_response_ids:
        return clock  # duplicate delivery — safe no-op

    if clock.state == ClockState.RESOLVED:
        if response_id is not None and response_id in clock.seen_response_ids:
            return clock  # duplicate after close — safe no-op
        # Closed clocks reject anything new: transition() raises
        # InvalidClockTransitionError (fail closed).
        return transition(
            clock, _RESPONSE_KIND_TO_EVENT[kind], response_id=response_id
        )

    kind_phase = {
        "ack": PHASE_ACK,
        "update": PHASE_UPDATE,
        "resolution": PHASE_RESOLUTION,
    }[kind]
    if kind_phase == PHASE_UPDATE and not clock.has_update_phase:
        raise InvalidClockTransitionError(
            "UPDATE response invalid: SLA carries no update obligation"
        )
    current_idx = _current_phase_index(clock)
    kind_idx = _phase_index_for_kind(kind, clock.has_update_phase)

    if kind == "resolution":
        # Resolution supersedes any pending phase (terminal, always allowed
        # from non-terminal states). Lateness is judged against the
        # resolution deadline.
        deadline = clock.deadlines.resolution_deadline
        late = not is_met(at, deadline)
        if clock.state in _WAITING_STATES and late:
            clock = transition(clock, ClockEvent.DEADLINE_PASSED)
        clock = transition(
            clock, ClockEvent.RESOLVED, response_id=response_id
        )
        return SLAClock(
            incident_id=clock.incident_id,
            tenant_id=clock.tenant_id,
            state=clock.state,
            phase=clock.phase,
            deadlines=clock.deadlines,
            has_update_phase=clock.has_update_phase,
            tier=clock.tier,
            breached_phase=clock.breached_phase,
            seen_response_ids=clock.seen_response_ids,
            escalations=clock.escalations,
            last_response_late=late,
        )

    if kind_idx < current_idx:
        return clock  # stale: phase already passed — safe no-op
    if kind_idx > current_idx:
        raise InvalidClockTransitionError(
            f"out-of-order vendor response: kind={kind!r} while phase={clock.phase!r}"
        )

    deadline = clock.deadlines.deadline_for(kind_phase)
    assert deadline is not None  # same-phase wait always has a deadline
    late = not is_met(at, deadline)
    if clock.state in _WAITING_STATES and late:
        clock = transition(clock, ClockEvent.DEADLINE_PASSED)
    clock = transition(
        clock, _RESPONSE_KIND_TO_EVENT[kind], response_id=response_id
    )
    return SLAClock(
        incident_id=clock.incident_id,
        tenant_id=clock.tenant_id,
        state=clock.state,
        phase=clock.phase,
        deadlines=clock.deadlines,
        has_update_phase=clock.has_update_phase,
        tier=clock.tier,
        breached_phase=clock.breached_phase,
        seen_response_ids=clock.seen_response_ids,
        escalations=clock.escalations,
        last_response_late=late,
    )


# ── 3. Wait description + signal-compatible waiter ────────────────────────


@dataclass(frozen=True)
class VendorWait:
    """Durable-wait arming parameters for the current clock position.

    ``deadline=None`` means a signal-only wait (no timer): used after
    escalation, where the workflow waits indefinitely for the late vendor
    response or human action.
    """

    signal: str
    deadline: datetime | None
    phase: str


def describe_wait(clock: SLAClock) -> VendorWait | None:
    """Return the wait to arm for ``clock`` (None when no wait applies).

    ``WAITING_*`` → timer + signal wait on the phase deadline.
    ``ESCALATED`` → signal-only wait for the late response.
    ``ACTIVE`` / ``BREACHED`` / ``RESOLVED`` → None (transient or terminal).
    """
    if clock.state in _WAITING_STATES:
        return VendorWait(
            signal=SLA_VENDOR_RESPONSE_SIGNAL,
            deadline=clock.deadlines.deadline_for(clock.phase),
            phase=clock.phase,
        )
    if clock.state == ClockState.ESCALATED:
        return VendorWait(
            signal=SLA_VENDOR_RESPONSE_SIGNAL, deadline=None, phase=clock.phase
        )
    return None


def phase_timeout_seconds(deadline: datetime, now: datetime) -> float:
    """Seconds from ``now`` until ``deadline`` (floored at 0; pure).

    The production starter computes per-phase ``wait_condition`` timeouts
    with this helper from core deadline instants — the workflow itself never
    invents durations.
    """
    return max(0.0, (deadline - now).total_seconds())


def build_phase_waits(
    deadlines: SLADeadlines, *, has_update_phase: bool
) -> tuple[VendorWait, ...]:
    """Ordered waits (ack → [update →] resolution) the workflow arms in turn."""
    waits = [
        VendorWait(
            signal=SLA_VENDOR_RESPONSE_SIGNAL,
            deadline=deadlines.ack_deadline,
            phase=PHASE_ACK,
        )
    ]
    if has_update_phase:
        waits.append(
            VendorWait(
                signal=SLA_VENDOR_RESPONSE_SIGNAL,
                deadline=deadlines.update_deadline,
                phase=PHASE_UPDATE,
            )
        )
    waits.append(
        VendorWait(
            signal=SLA_VENDOR_RESPONSE_SIGNAL,
            deadline=deadlines.resolution_deadline,
            phase=PHASE_RESOLUTION,
        )
    )
    return tuple(waits)


class InMemorySLAWaiter:
    """In-memory vendor-response waiter mirroring ``SignalHandler``.

    Structural compatibility: ``emit(name, payload)`` /
    ``await_decision(name)`` / ``resolve(decision)`` — satisfies the
    ``src.mission.signal_handler.SignalHandler`` protocol, so the Temporal
    workflow signal transport can substitute it without changing callers.
    Deliberate difference (tested): resolved responses are queued, so a
    ``resolve`` that lands before any awaiter is delivered to the next
    ``await_decision`` instead of being dropped. No timers, no sleep loops,
    no polling, no I/O, no LLM.
    """

    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict[str, Any]]] = []
        self._queued: list[dict[str, Any]] = []
        self._futures: list[asyncio.Future[dict[str, Any]]] = []

    def emit(self, name: str, payload: dict[str, Any]) -> None:
        """Record the signal (instant — tests can inspect ``emitted``)."""
        self.emitted.append((name, payload))

    async def await_decision(self, name: str) -> dict[str, Any]:
        """Suspend until :meth:`resolve` delivers a vendor response."""
        if self._queued:
            return self._queued.pop(0)
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._futures.append(fut)
        return await fut

    async def await_response(self, name: str) -> dict[str, Any]:
        """Alias of :meth:`await_decision` with SLA-domain naming."""
        return await self.await_decision(name)

    def resolve(self, decision: dict[str, Any]) -> None:
        """Deliver ``decision`` to every pending awaiter and queue a copy."""
        for fut in list(self._futures):
            if not fut.done():
                fut.set_result(decision)
        self._futures.clear()
        self._queued.append(decision)

    def resolve_vendor_response(self, response: dict[str, Any]) -> None:
        """Alias of :meth:`resolve` with SLA-domain naming."""
        self.resolve(response)
