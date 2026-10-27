"""Phase 5 — SLAClockWorkflow (Temporal binding for the SLA clock engine).

Substrate verdict (see module docstring of ``src.mission.sla_clocks``):
durable timers + signals live in **both** Temporal substrates today — Go
hosts the production-proven waits (``AwaitWithTimeout`` + ``GetSignalChannel``
in ``business_os_workflow.go`` HITL gate and ``onboarding_workflow.go``),
and Python hosts ``temporalio`` workflows (``src/workflows/*.py``,
``src/worker.py``). This binding uses the **Python ``temporalio`` substrate**
because the SLA domain (``SLA`` / ``EscalationPolicy`` / ``Incident`` field
names) and the ``SignalHandler`` interface it mirrors both live in Python —
so no cross-process plumbing is needed and no new framework is introduced.

Waiting strategy (no polling anywhere):

* Each clock phase arms ``workflow.wait_condition`` with a ``timeout`` — the
  **durable timer** — raced against the ``vendor_response`` **signal**
  wake-up (``sla-vendor-response``).
* On ``asyncio.TimeoutError`` the workflow records ``DEADLINE_PASSED`` →
  ``BREACHED`` → ``ESCALATE`` via the pure core, then re-arms a signal-only
  ``wait_condition`` (``timeout=None`` creates no timer) for the late vendor
  response. Post-escalation arrivals are therefore accepted late, never lost.
* Time ownership: the workflow never reads a wall clock. The race verdict
  derives from the timer outcome itself (met ⇒ ``at = deadline``,
  timed-out ⇒ ``at = deadline + 1s``) and every deadline/transition/ladder
  decision delegates to :mod:`src.mission.sla_clocks`. Temporal owns time;
  neither the LLM, the vendor, nor the workflow does.

Production seam (documented, NOT wired here — ``worker.py``'s 6-canonical
roster is frozen by ``tests/unit/test_worker_registration.py``):

* Starter (Go core or scheduler): on incident detection, compute deadlines
  with ``compute_sla_deadlines`` / ``deadlines_for_sla``, convert the policy
  with ``ladder_from_policy``, derive per-phase timeouts with
  ``phase_timeout_seconds(deadline, started_at)``, and start this workflow
  with :func:`build_workflow_input`.
* Registration: add ``SLAClockWorkflow`` to ``_build_workflow_list`` (and its
  escalation-notify activities when they exist) — a Phase 6 step.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from src.mission import sla_clocks
    from src.mission.sla_clocks import (
        PHASE_ACK,
        PHASE_RESOLUTION,
        PHASE_UPDATE,
        SLA_VENDOR_RESPONSE_SIGNAL,
        ClockEvent,
        ClockState,
    )


WORKFLOW_NAME = "SLAClockWorkflow"

_KIND_FOR_PHASE = {
    PHASE_ACK: "ack",
    PHASE_UPDATE: "update",
    PHASE_RESOLUTION: "resolution",
}


def build_workflow_input(
    *,
    incident_id: str,
    tenant_id: str,
    detected_at: datetime,
    acknowledgement_minutes: int,
    update_minutes: int | None,
    resolution_minutes: int,
    business_calendar: str = "24x7",
    ladder: dict[str, Any] | None = None,
    phase_timeouts: dict[str, float] | None = None,
    signal: str = SLA_VENDOR_RESPONSE_SIGNAL,
) -> dict[str, Any]:
    """Build the workflow input dict (pure; starter-side helper).

    ``phase_timeouts`` maps each phase to its ``wait_condition`` timeout in
    seconds, normally derived via ``phase_timeout_seconds`` at dispatch. When
    omitted, minute budgets are used as-is (correct when the workflow starts
    at detection time).
    """
    timeouts: dict[str, float] = dict(phase_timeouts or {})
    timeouts.setdefault(PHASE_ACK, float(acknowledgement_minutes * 60))
    if update_minutes is not None:
        timeouts.setdefault(PHASE_UPDATE, float(update_minutes * 60))
    timeouts.setdefault(PHASE_RESOLUTION, float(resolution_minutes * 60))
    return {
        "incident_id": incident_id,
        "tenant_id": tenant_id,
        "detected_at": detected_at.isoformat(),
        "acknowledgement_minutes": acknowledgement_minutes,
        "update_minutes": update_minutes,
        "resolution_minutes": resolution_minutes,
        "business_calendar": business_calendar,
        "ladder": dict(ladder or {}),
        "phase_timeouts": timeouts,
        "signal": signal,
    }


@workflow.defn(name=WORKFLOW_NAME)
class SLAClockWorkflow:
    """Durable incident-SLA wait: timer + vendor-response signal, no polling."""

    def __init__(self) -> None:
        self._pending: list[dict[str, Any]] = []
        self._seen_ids: list[str] = []
        self._clock_state: str = ClockState.ACTIVE.value
        self._phase: str = PHASE_ACK
        self._tier: int = 0
        self._escalations: list[dict[str, Any]] = []

    def _has_response_for(self, phase: str) -> bool:
        wanted = _KIND_FOR_PHASE[phase]
        return any(
            r.get("kind") == wanted or r.get("kind") == "resolution"
            for r in self._pending
        )

    def _pop_response_for(self, phase: str) -> dict[str, Any]:
        wanted = _KIND_FOR_PHASE[phase]
        for i, response in enumerate(self._pending):
            if response.get("kind") == wanted or response.get("kind") == "resolution":
                return self._pending.pop(i)
        raise RuntimeError(f"no queued vendor response for phase {phase!r}")

    @workflow.signal
    async def vendor_response(self, response: dict[str, Any]) -> None:
        """Vendor-response wake-up (``sla-vendor-response``).

        Dedupes by ``response_id`` so duplicate deliveries never double-apply;
        id-less redeliveries are kept (the core judges them deterministically).
        """
        response_id = response.get("response_id")
        if response_id is not None and response_id in self._seen_ids:
            workflow.logger.info(
                "SLAClockWorkflow: duplicate vendor response ignored",
                extra={"response_id": response_id},
            )
            return
        if response_id is not None:
            self._seen_ids.append(response_id)
        self._pending.append(dict(response))

    @workflow.query
    def current_state(self) -> dict[str, Any]:
        """Queryable clock position (state, phase, tier, escalations)."""
        return {
            "state": self._clock_state,
            "phase": self._phase,
            "tier": self._tier,
            "escalations": list(self._escalations),
            "pending_responses": len(self._pending),
        }

    @workflow.run
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Wait out each SLA phase on timer + signal; escalate on breach."""
        detected_at = datetime.fromisoformat(input_data["detected_at"])
        # Unsupported calendars fail the workflow fast — never silent math.
        deadlines = sla_clocks.compute_sla_deadlines(
            detected_at,
            acknowledgement_minutes=input_data["acknowledgement_minutes"],
            update_minutes=input_data.get("update_minutes"),
            resolution_minutes=input_data["resolution_minutes"],
            business_calendar=input_data.get("business_calendar", "24x7"),
        )
        has_update_phase = input_data.get("update_minutes") is not None
        ladder = sla_clocks.EscalationLadder(
            t0_vendor_primary=input_data["ladder"].get("t0_vendor_primary", ""),
            t1_vendor_escalation=input_data["ladder"].get("t1_vendor_escalation", ""),
            t2_internal_owner=input_data["ladder"].get("t2_internal_owner", ""),
            t3_hitl_material=input_data["ladder"].get("t3_hitl_material", ""),
            requires_hitl=input_data["ladder"].get("requires_hitl", True),
        )
        timeouts: dict[str, float] = input_data.get("phase_timeouts", {})

        clock = sla_clocks.open_clock(
            input_data["incident_id"],
            input_data["tenant_id"],
            deadlines,
            has_update_phase=has_update_phase,
        )
        clock = sla_clocks.transition(clock, ClockEvent.START)

        phases = [w.phase for w in sla_clocks.build_phase_waits(deadlines, has_update_phase=has_update_phase)]
        for phase in phases:
            deadline = deadlines.deadline_for(phase)
            assert deadline is not None  # built phases always have deadlines
            timeout = float(timeouts.get(phase, 0.0))

            # ── Durable timer raced against the signal wake-up ──────────
            timed_out = False
            try:
                signalled = await workflow.wait_condition(
                    lambda: self._has_response_for(phase),
                    timeout=timedelta(seconds=timeout),
                )
                if not signalled:
                    timed_out = True
            except asyncio.TimeoutError:
                timed_out = True

            if timed_out:
                clock = sla_clocks.transition(clock, ClockEvent.DEADLINE_PASSED)
                clock = sla_clocks.escalate(clock, ladder)
                last = clock.escalations[-1]
                self._escalations.append(dict(last))
                self._clock_state = clock.state.value
                self._phase = clock.phase
                self._tier = clock.tier
                workflow.logger.warn(
                    "SLAClockWorkflow: deadline breached; escalated",
                    extra={"phase": phase, "tier": clock.tier},
                )
                # Signal-only wait for the late response (no timer, no poll).
                await workflow.wait_condition(lambda: self._has_response_for(phase))

            response = self._pop_response_for(phase)
            # Race verdict from the timer outcome — no wall clock in here.
            at = deadline if not timed_out else deadline + timedelta(seconds=1)
            clock = sla_clocks.apply_vendor_response(clock, response, at=at)
            self._clock_state = clock.state.value
            self._phase = clock.phase
            self._tier = clock.tier

        return {
            "incident_id": clock.incident_id,
            "tenant_id": clock.tenant_id,
            "final_state": clock.state.value,
            "tier": clock.tier,
            "escalations": list(self._escalations),
            "late_responses": clock.last_response_late,
        }
