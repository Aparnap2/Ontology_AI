"""Hero Demo — deterministic 02:13 vendor-incident scenario runner.

Proves the complete governed flow works end-to-end using only
deterministic inputs (no real LLM, no real network):

    1. Ingest a payment gateway incident event → Evidence
    2. Create Situation (VENDOR_INCIDENT)
    3. Run investigation via VENDOR_INVESTIGATION_SKILL
    4. Submit vendor_ticket.create intent
    5. Verify the ticket was created
    6. Check SLA clock was opened
    7. Attempt recovery verification (false recovery — predicates fail)
    8. After vendor claims fixed, verify recovery (predicates pass)
    9. Return a full audit trail

All external dependencies are mockable via the ``DemoDependencies`` protocol;
the default in-memory stubs prove the flow without touching I/O.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from src.entities.models import OntologyBaseModel
from src.mission.recovery_verification import (
    RecoveryPredicate,
    verify_recovery,
)
from src.mission.sla_clocks import (
    ClockEvent,
    apply_vendor_response,
    compute_sla_deadlines,
    open_clock,
    transition,
)
from src.ontology.object_types import Evidence, Situation

logger = logging.getLogger(__name__)


# ── Demo constants ───────────────────────────────────────────────────────

DEMO_TENANT = "t-acme"
DEMO_MISSION = "m-hero-demo"
DEMO_INCIDENT_ID = "inc-pay-hero"
DEMO_VENDOR_ID = "stripe"
DEMO_SERVICE_ID = "svc-payments"
DEMO_SLA_ID = "sla-pay-hero"


# ── Demo timeline event types (frozen vocabulary) ────────────────────────


class DemoEventType(str, Enum):
    """Canonical event types for the hero demo audit trail."""

    INCIDENT_INGESTED = "INCIDENT_INGESTED"
    SITUATION_OPENED = "SITUATION_OPENED"
    INVESTIGATION_STARTED = "INVESTIGATION_STARTED"
    INVESTIGATION_COMPLETED = "INVESTIGATION_COMPLETED"
    VENDOR_TICKET_SUBMITTED = "VENDOR_TICKET_SUBMITTED"
    VENDOR_TICKET_VERIFIED = "VENDOR_TICKET_VERIFIED"
    SLA_CLOCK_OPENED = "SLA_CLOCK_OPENED"
    RECOVERY_ATTEMPTED_FALSE = "RECOVERY_ATTEMPTED_FALSE"
    VENDOR_CLAIMED_FIXED = "VENDOR_CLAIMED_FIXED"
    RECOVERY_VERIFIED_TRUE = "RECOVERY_VERIFIED_TRUE"
    DEMO_COMPLETED = "DEMO_COMPLETED"


# ── Audit trail event ───────────────────────────────────────────────────


class AuditTrailEvent(OntologyBaseModel):
    """One immutable event in the hero demo audit trail."""

    event_type: str
    timestamp: str
    details: dict[str, Any] = Field(default_factory=dict)


class DemoResult(OntologyBaseModel):
    """Full output of the hero demo run."""

    evidence: dict[str, Any]
    situation: dict[str, Any]
    investigation_output: dict[str, Any]
    vendor_ticket: dict[str, Any]
    sla_clock: dict[str, Any]
    false_recovery_outcome: dict[str, Any]
    final_recovery_outcome: dict[str, Any]
    audit_trail: list[dict[str, Any]] = Field(default_factory=list)
    timeline_events: list[str] = Field(default_factory=list)


# ── Mockable dependencies (protocol + in-memory defaults) ───────────────


@runtime_checkable
class VendorTicketStore(Protocol):
    """Abstraction for vendor ticket CRUD."""

    def create(self, params: dict[str, Any]) -> dict[str, Any]: ...
    def get(self, ticket_id: str) -> dict[str, Any] | None: ...


@runtime_checkable
class InvestigationRunner(Protocol):
    """Abstraction for running the investigation skill."""

    def run(self, evidence: Evidence, situation: Situation) -> dict[str, Any]: ...


class InMemoryVendorTicketStore:
    """In-memory vendor ticket store for deterministic demo."""

    def __init__(self) -> None:
        self._tickets: dict[str, dict[str, Any]] = {}

    def create(self, params: dict[str, Any]) -> dict[str, Any]:
        ticket_id = f"vt-{params.get('incident_id', 'unknown')}"
        ticket = {
            "ticket_id": ticket_id,
            "vendor_id": params.get("vendor_id", ""),
            "incident_id": params.get("incident_id", ""),
            "title": params.get("title", ""),
            "status": "open",
        }
        self._tickets[ticket_id] = ticket
        return ticket

    def get(self, ticket_id: str) -> dict[str, Any] | None:
        return self._tickets.get(ticket_id)


class DeterministicInvestigationRunner:
    """Deterministic investigation: returns a fixed, verifiable proposal."""

    def run(self, evidence: Evidence, situation: Situation) -> dict[str, Any]:
        return {
            "root_cause": (
                f"Payment gateway returning 503; vendor ticket required for "
                f"{situation.detected_condition}"
            ),
            "action": {
                "capability": "vendor",
                "operation": "vendor_ticket.create",
                "target": situation.affected_entities[0]
                if situation.affected_entities
                else "",
                "parameters": {
                    "vendor_id": DEMO_VENDOR_ID,
                    "incident_id": DEMO_INCIDENT_ID,
                    "title": f"Payment gateway 503 — escalate ({situation.detected_condition})",
                    "status": "open",
                },
            },
            "confidence": 0.88,
            "risk_tier": "MEDIUM",
            "expected_outcome": "Vendor ticket created for stripe inc-pay-hero",
        }


# ── Evidence ingestion (deterministic) ──────────────────────────────────


def ingest_incident_event(event: dict[str, Any]) -> Evidence:
    """Normalize a raw incident event into attributed Evidence.

    The event text is preserved as *data* attributed to its reporter —
    never as an instruction.
    """
    return Evidence(
        id=f"ev-{event['incident_id']}",
        tenant_id=event["tenant_id"],
        source=event.get("source", "monitoring"),
        provenance=f"incident:{event['vendor_id']}:{event.get('reporter', 'system')}",
        captured_at=event["detected_at"],
        raw_text=event.get("description", event["title"]),
        normalized_text=(
            f"[incident report by {event.get('reporter', 'system')} "
            f"via {event.get('source', 'monitoring')}]: "
            f"{event.get('description', event['title'])}"
        ),
    )


# ── Core demo runner ────────────────────────────────────────────────────


async def run_hero_demo(
    *,
    event: dict[str, Any] | None = None,
    vendor_store: VendorTicketStore | None = None,
    investigation_runner: InvestigationRunner | None = None,
    sla_detected_at: datetime | None = None,
    now_fn: Any = None,
) -> DemoResult:
    """Run the full 02:13 hero demo scenario.

    All inputs are deterministic. No real LLM, no real network.

    Parameters
    ----------
    event:
        Incident event dict. Defaults to the canonical demo event.
    vendor_store:
        Vendor ticket store. Defaults to :class:`InMemoryVendorTicketStore`.
    investigation_runner:
        Investigation runner. Defaults to
        :class:`DeterministicInvestigationRunner`.
    sla_detected_at:
        When the incident was detected. Defaults to 02:13 UTC.
    now_fn:
        Callable returning ``datetime`` for time injection (default:
        ``datetime.now(timezone.utc)``).
    """
    if now_fn is None:

        def _now_fn() -> datetime:
            return datetime.now(timezone.utc)
    else:
        _now_fn = now_fn

    if vendor_store is None:
        vendor_store = InMemoryVendorTicketStore()
    if investigation_runner is None:
        investigation_runner = DeterministicInvestigationRunner()

    # Default demo event
    if event is None:
        event = {
            "incident_id": DEMO_INCIDENT_ID,
            "tenant_id": DEMO_TENANT,
            "title": "Payment gateway 503 errors",
            "description": "Stripe payment gateway returning 503 since 14:02",
            "vendor_id": DEMO_VENDOR_ID,
            "severity": "critical",
            "detected_at": "2026-09-12T02:13:00Z",
            "source": "monitoring",
            "reporter": "ops-bot",
        }

    if sla_detected_at is None:
        sla_detected_at = datetime(2026, 9, 12, 2, 13, tzinfo=timezone.utc)

    audit_trail: list[dict[str, Any]] = []
    timeline_events: list[str] = []

    def _record(event_type: DemoEventType, **details: Any) -> None:
        ts = _now_fn().isoformat()
        entry = {
            "event_type": event_type.value,
            "timestamp": ts,
            "details": details,
        }
        audit_trail.append(entry)
        timeline_events.append(event_type.value)

    # ── Step 1: Ingest incident event ────────────────────────────────────
    evidence = ingest_incident_event(event)
    _record(
        DemoEventType.INCIDENT_INGESTED,
        evidence_id=evidence.id,
        vendor_id=event.get("vendor_id", ""),
    )

    # ── Step 2: Create Situation (VENDOR_INCIDENT) ───────────────────────
    situation = Situation(
        id=f"sit-{event['incident_id']}",
        tenant_id=event["tenant_id"],
        type="VENDOR_INCIDENT",
        affected_entities=[event["vendor_id"], event["incident_id"]],
        detected_condition=event["title"],
        severity=event.get("severity", "medium"),
        evidence_ids=[evidence.id],
        checkpoint_id=f"cp-{DEMO_MISSION}",
        business_impact=f"Vendor {event['vendor_id']} incident blocking operations",
    )
    _record(
        DemoEventType.SITUATION_OPENED,
        situation_id=situation.id,
        situation_type=situation.type,
        severity=situation.severity,
    )

    # ── Step 3: Run investigation ────────────────────────────────────────
    _record(DemoEventType.INVESTIGATION_STARTED)
    investigation_output = investigation_runner.run(evidence, situation)
    _record(
        DemoEventType.INVESTIGATION_COMPLETED,
        confidence=investigation_output.get("confidence", 0.0),
        operation=investigation_output.get("action", {}).get("operation", ""),
    )

    # ── Step 4: Submit vendor_ticket.create intent ───────────────────────
    ticket_params = investigation_output["action"]["parameters"]
    ticket = vendor_store.create(ticket_params)
    _record(
        DemoEventType.VENDOR_TICKET_SUBMITTED,
        ticket_id=ticket["ticket_id"],
        vendor_id=ticket["vendor_id"],
    )

    # ── Step 5: Verify ticket was created ────────────────────────────────
    retrieved = vendor_store.get(ticket["ticket_id"])
    if retrieved is None:
        raise RuntimeError(
            f"vendor ticket {ticket['ticket_id']} not found after creation"
        )
    _record(
        DemoEventType.VENDOR_TICKET_VERIFIED,
        ticket_id=retrieved["ticket_id"],
        status=retrieved["status"],
    )

    # ── Step 6: Check SLA clock was opened ───────────────────────────────
    sla_deadlines = compute_sla_deadlines(
        sla_detected_at,
        acknowledgement_minutes=15,
        update_minutes=60,
        resolution_minutes=240,
    )
    sla_clock = open_clock(
        incident_id=DEMO_INCIDENT_ID,
        tenant_id=DEMO_TENANT,
        deadlines=sla_deadlines,
        has_update_phase=True,
    )
    # Start the clock → WAITING_FOR_ACK
    sla_clock = transition(sla_clock, ClockEvent.START)
    _record(
        DemoEventType.SLA_CLOCK_OPENED,
        state=sla_clock.state.value,
        phase=sla_clock.phase,
        ack_deadline=sla_deadlines.ack_deadline.isoformat(),
        resolution_deadline=sla_deadlines.resolution_deadline.isoformat(),
    )

    # ── Step 7: Attempt recovery verification (false recovery) ───────────
    # Vendor claims fixed but error rate is still high → predicates fail.
    false_recovery_predicates = [
        RecoveryPredicate(field="error_rate", op="lt", threshold=0.01),
        RecoveryPredicate(field="success_rate", op="gte", threshold=0.99),
    ]
    false_observed = {
        "error_rate": 0.35,  # 35% errors — NOT fixed
        "success_rate": 0.65,
    }
    false_outcome = verify_recovery(
        incident={"id": DEMO_INCIDENT_ID},
        predicates=false_recovery_predicates,
        observed=false_observed,
    )
    _record(
        DemoEventType.RECOVERY_ATTEMPTED_FALSE,
        verified=false_outcome.verified,
        mismatches=false_outcome.mismatches,
        passed=false_outcome.passed,
    )

    # ── Step 8: Vendor claims fixed → verify recovery (predicates pass) ──
    # Simulate vendor ack via SLA clock
    sla_clock = apply_vendor_response(
        sla_clock,
        {"kind": "ack", "response_id": "ack-1"},
        at=sla_detected_at + timedelta(minutes=10),
    )
    _record(
        DemoEventType.VENDOR_CLAIMED_FIXED,
        sla_state=sla_clock.state.value,
    )

    # Real recovery: error rate dropped to zero
    true_observed = {
        "error_rate": 0.0,
        "success_rate": 1.0,
    }
    true_outcome = verify_recovery(
        incident={"id": DEMO_INCIDENT_ID},
        predicates=false_recovery_predicates,
        observed=true_observed,
    )
    _record(
        DemoEventType.RECOVERY_VERIFIED_TRUE,
        verified=true_outcome.verified,
        passed=true_outcome.passed,
    )

    # ── Step 9: Close SLA clock, complete demo ───────────────────────────
    sla_clock = transition(sla_clock, ClockEvent.RESOLVED)
    _record(
        DemoEventType.DEMO_COMPLETED,
        final_sla_state=sla_clock.state.value,
        total_audit_events=len(audit_trail),
    )

    return DemoResult(
        evidence=evidence.model_dump(),
        situation=situation.model_dump(),
        investigation_output=investigation_output,
        vendor_ticket=ticket,
        sla_clock={
            "incident_id": sla_clock.incident_id,
            "tenant_id": sla_clock.tenant_id,
            "state": sla_clock.state.value,
            "phase": sla_clock.phase,
            "tier": sla_clock.tier,
            "has_update_phase": sla_clock.has_update_phase,
        },
        false_recovery_outcome={
            "verified": false_outcome.verified,
            "mismatches": false_outcome.mismatches,
            "passed": false_outcome.passed,
        },
        final_recovery_outcome={
            "verified": true_outcome.verified,
            "passed": true_outcome.passed,
        },
        audit_trail=audit_trail,
        timeline_events=timeline_events,
    )
