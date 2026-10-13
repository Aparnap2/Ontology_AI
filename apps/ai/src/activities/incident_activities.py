"""V7 Incident Activities — Temporal activity wrappers for the hero path.

Each activity is a thin wrapper over the existing deterministic V7 library
modules (hero_demo, recovery_verification, sla_clocks, control_plane).
No real network, no real LLM — all deterministic, all testable.

The activities convert between dict wire format (Temporal serialization)
and the Pydantic/domain objects the V7 library expects.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from temporalio import activity

from src.mission.hero_demo import (
    InMemoryVendorTicketStore,
    DeterministicInvestigationRunner,
    ingest_incident_event,
)
from src.mission.recovery_verification import (
    RecoveryPredicate,
    verify_recovery,
    RecoveryOutcome,
)
from src.control_plane.contracts import ActionIntent
from src.control_plane.ingress import submit_intent as _submit_intent
from src.ontology.object_types import Situation

log = logging.getLogger(__name__)

# Module-level stores shared across activities within a single worker process.
# In production these would be durable; the scaffold uses in-memory.
_vendor_store = InMemoryVendorTicketStore()
_investigation_runner = DeterministicInvestigationRunner()


def _safe_heartbeat(message: str) -> None:
    """Safely call activity.heartbeat, ignoring errors outside activity context."""
    try:
        activity.heartbeat(message)
    except RuntimeError:
        log.debug("Heartbeat (no context): %s", message)


# ---------------------------------------------------------------------------
# Activity 1: create_situation
# ---------------------------------------------------------------------------


@activity.defn(name="create_situation")
async def create_situation(incident_data: dict[str, Any]) -> dict[str, Any]:
    """Create a Situation from incoming incident data.

    Ingests the incident event as Evidence, then constructs a Situation
    using the ontology model.
    """
    _safe_heartbeat("Creating situation from incident")
    log.info(
        "create_situation: incident_id=%s tenant_id=%s",
        incident_data.get("incident_id", ""),
        incident_data.get("tenant_id", ""),
    )

    # Step 1: Ingest incident as Evidence
    evidence = ingest_incident_event(incident_data)

    # Step 2: Build Situation
    situation = Situation(
        id=f"sit-{incident_data['incident_id']}",
        tenant_id=incident_data["tenant_id"],
        type="VENDOR_INCIDENT",
        affected_entities=[
            incident_data.get("vendor_id", ""),
            incident_data["incident_id"],
        ],
        detected_condition=incident_data.get("title", ""),
        severity=incident_data.get("severity", "medium"),
        evidence_ids=[evidence.id],
        checkpoint_id=f"cp-{incident_data.get('mission_id', 'default')}",
        business_impact=(
            f"Vendor {incident_data.get('vendor_id', '')} incident blocking operations"
        ),
    )

    return situation.model_dump()


# ---------------------------------------------------------------------------
# Activity 2: assemble_checkpoint
# ---------------------------------------------------------------------------


@activity.defn(name="assemble_checkpoint")
async def assemble_checkpoint(situation: dict[str, Any]) -> dict[str, Any]:
    """Assemble a ContextCheckpoint from the Situation.

    In the deterministic scaffold this is a simple dict aggregation.
    """
    _safe_heartbeat("Assembling context checkpoint")
    log.info("assemble_checkpoint: situation_id=%s", situation.get("id", ""))

    checkpoint = {
        "checkpoint_id": situation.get("checkpoint_id", "cp-default"),
        "situation_id": situation["id"],
        "tenant_id": situation["tenant_id"],
        "situation_type": situation.get("type", "VENDOR_INCIDENT"),
        "severity": situation.get("severity", "medium"),
        "affected_entities": situation.get("affected_entities", []),
        "evidence_ids": situation.get("evidence_ids", []),
        "business_impact": situation.get("business_impact", ""),
        "assembled_at": datetime.now(timezone.utc).isoformat(),
    }
    return checkpoint


# ---------------------------------------------------------------------------
# Activity 3: run_investigation
# ---------------------------------------------------------------------------


@activity.defn(name="run_investigation")
async def run_investigation(checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Run deterministic investigation (no LLM).

    Uses the DeterministicInvestigationRunner from hero_demo.
    """
    _safe_heartbeat("Running investigation")
    log.info("run_investigation: situation_id=%s", checkpoint.get("situation_id", ""))

    # Rebuild the Situation object from the checkpoint
    situation = Situation(
        id=checkpoint["situation_id"],
        tenant_id=checkpoint["tenant_id"],
        type=checkpoint.get("situation_type", "VENDOR_INCIDENT"),
        affected_entities=checkpoint.get("affected_entities", []),
        detected_condition=checkpoint.get("business_impact", ""),
        severity=checkpoint.get("severity", "medium"),
        evidence_ids=checkpoint.get("evidence_ids", []),
        checkpoint_id=checkpoint.get("checkpoint_id", ""),
        business_impact=checkpoint.get("business_impact", ""),
    )

    # Build minimal Evidence object for the runner
    from src.ontology.object_types import Evidence

    evidence = Evidence(
        id=checkpoint.get("evidence_ids", ["ev-unknown"])[0]
        if checkpoint.get("evidence_ids")
        else "ev-unknown",
        tenant_id=checkpoint["tenant_id"],
        source="monitoring",
        provenance="incident:system:monitoring",
        captured_at=datetime.now(timezone.utc).isoformat(),
        raw_text=checkpoint.get("business_impact", ""),
        normalized_text=checkpoint.get("business_impact", ""),
    )

    return _investigation_runner.run(evidence, situation)


# ---------------------------------------------------------------------------
# Activity 4: generate_action_intent
# ---------------------------------------------------------------------------


@activity.defn(name="generate_action_intent")
async def generate_action_intent(
    investigation_result: dict[str, Any],
) -> dict[str, Any]:
    """Generate an ActionIntent dict from investigation output.

    Builds a valid ActionIntent that can be submitted to the control plane.
    """
    _safe_heartbeat("Generating action intent")
    log.info(
        "generate_action_intent: operation=%s",
        investigation_result.get("action", {}).get("operation", ""),
    )

    action = investigation_result.get("action", {})
    params = action.get("parameters", {})

    intent = ActionIntent(
        capability=action.get("capability", "vendor"),
        operation=action.get("operation", "vendor_ticket.create"),
        target_reference=action.get("target", ""),
        requested_parameters=params,
        reason=investigation_result.get(
            "root_cause", "Incident requires vendor ticket"
        ),
        evidence_ids=[],
        expected_outcome=investigation_result.get(
            "expected_outcome", "Vendor ticket created"
        ),
        confidence=float(investigation_result.get("confidence", 0.0)),
        requested_by="IncidentWorkflow",
    )

    return intent.model_dump()


# ---------------------------------------------------------------------------
# Activity 5: submit_to_control_plane
# ---------------------------------------------------------------------------


#: LAST-RESORT fallback only. Real invocations MUST pass server-owned identity:
#: authority is derived from trusted state, so substituting a constant here
#: means authorizing every caller under one tenant's permissions. The incident
#: workflow now builds its context from the incoming incident
#: (see src/workflows/incident_workflow.py).
DEFAULT_TRUSTED_CONTEXT: dict[str, Any] = {
    "tenant_id": "t-acme",
    "mission_id": "m-hero-demo",
    "employee_id": "emp-incident",
    "actor_identity": "IncidentWorkflow",
    "permissions": [
        "vendor_ticket.create",
        "vendor_ticket.read",
        "situation.create",
        "situation.update",
    ],
}

#: Control-plane decisions that represent a genuine execution.
EXECUTED_DECISIONS = frozenset({"permit:executed"})


@activity.defn(name="submit_to_control_plane")
async def submit_to_control_plane(
    action_intent: dict[str, Any],
    trusted_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Submit through the control plane: authorize, policy, idempotency, execute.

    Reports the control plane's decision HONESTLY. ``submitted`` is True only
    when the control plane actually accepted and executed the intent; a
    rejection (``deny:*``, ``require_approval:*``) or a raised exception is
    never reported as success.

    Exceptions are deliberately NOT swallowed — a control-plane failure must
    surface to the caller and to Temporal's retry/alerting rather than being
    converted into a success signal.
    """
    _safe_heartbeat("Submitting to control plane")
    log.info(
        "submit_to_control_plane: operation=%s",
        action_intent.get("operation", ""),
    )

    intent = ActionIntent.model_validate(action_intent)
    context = dict(trusted_context or DEFAULT_TRUSTED_CONTEXT)

    result = await _submit_intent(intent, context)

    decision = str(result.get("decision", "")) if isinstance(result, dict) else ""
    accepted = decision in EXECUTED_DECISIONS
    if not accepted:
        log.warning(
            "control plane did not execute intent: decision=%s", decision or "<none>"
        )

    return {
        "intent": action_intent,
        "control_plane_result": result,
        "decision": decision,
        "accepted": accepted,
        "submitted": accepted,
    }


# ---------------------------------------------------------------------------
# Activity 6: execute_capability
# ---------------------------------------------------------------------------


@activity.defn(name="execute_capability")
async def execute_capability(authorized: dict[str, Any]) -> dict[str, Any]:
    """Execute the capability (create vendor ticket).

    Uses the InMemoryVendorTicketStore from hero_demo.
    """
    _safe_heartbeat("Executing capability")
    log.info("execute_capability: creating vendor ticket")

    intent_data = authorized.get("intent", {})
    params = intent_data.get("requested_parameters", {})

    ticket = _vendor_store.create(params)

    return {
        "vendor_ticket": ticket,
        "capability_executed": True,
    }


# ---------------------------------------------------------------------------
# Activity 7: verify_recovery
# ---------------------------------------------------------------------------


#: Payload key carrying independently-observed system state. There is
#: deliberately no default: the vendor's ticket status is the *claim under*
#: verification, so it can never also serve as evidence for it.
OBSERVED_EVIDENCE_KEY = "observed"


def _is_evidence(observed: Any) -> bool:
    """True only for a real observation carrying at least one numeric metric.

    ``{}``, ``None`` and dicts whose values are all ``None`` are the *absence*
    of evidence. They must never be read as a pass.
    """
    if not isinstance(observed, dict) or not observed:
        return False
    return any(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in observed.values()
    )


@activity.defn(name="verify_recovery")
async def verify_recovery_activity(data: dict[str, Any]) -> dict[str, Any]:
    """Verify recovery using predicate-based checks against observed state.

    Fails closed. The vendor's ticket status is the claim under verification
    and is never trusted as evidence for it. This activity previously read
    ``vendor_ticket.status`` and fabricated ``{"error_rate": 0.0,
    "success_rate": 1.0}`` whenever it looked resolved, then verified that
    invention against the predicates — reporting a successful recovery while
    the service was in total outage. It could not fail during a real outage.

    ``data["observed"]`` must be supplied by an independent monitoring source.
    Without it the verdict is INDETERMINATE — never VERIFIED, and never a
    silent False either, so an operator can tell "we checked and it failed"
    from "we never had evidence to check with".
    """
    _safe_heartbeat("Verifying recovery")
    log.info("verify_recovery_activity: checking predicates")

    incident_id = data.get("situation", {}).get("id", "unknown")

    # Predicates are fixed health thresholds; the observed values they are
    # checked against must come from outside this process.
    predicates = [
        RecoveryPredicate(field="error_rate", op="lt", threshold=0.01),
        RecoveryPredicate(field="success_rate", op="gte", threshold=0.99),
    ]

    observed = data.get(OBSERVED_EVIDENCE_KEY)
    if not _is_evidence(observed):
        log.warning(
            "verify_recovery_activity: no independent evidence for %s; "
            "refusing to certify recovery from the vendor's own claim",
            incident_id,
        )
        return {
            "verified": False,
            "state": "INDETERMINATE",
            "reason": (
                "no_independent_evidence: recovery cannot be verified from the "
                f"vendor's own claim; supply {OBSERVED_EVIDENCE_KEY!r} metrics "
                "from a monitoring source"
            ),
            "incident_id": incident_id,
            "mismatches": ["no_evidence_source"],
            "passed": [],
        }

    outcome: RecoveryOutcome = verify_recovery(
        incident={"id": incident_id},
        predicates=predicates,
        observed=observed,
    )

    return {
        "verified": outcome.verified,
        "state": "VERIFIED" if outcome.verified else "NOT_VERIFIED",
        "reason": "" if outcome.verified else "predicates_failed",
        "incident_id": outcome.incident_id,
        "mismatches": outcome.mismatches,
        "passed": outcome.passed,
    }


# ---------------------------------------------------------------------------
# Activity 8: resolve_situation
# ---------------------------------------------------------------------------


@activity.defn(name="resolve_situation")
async def resolve_situation(situation: dict[str, Any]) -> dict[str, Any]:
    """Mark the situation resolved — only behind a substantiated recovery.

    Emitting RESOLVED is itself a recovery claim. The workflow gates this on
    ``recovery.verified``, but that gate belonged to the caller, so the
    activity would certify a resolution when invoked directly. The evidence
    now travels with the payload and the gate lives with the claim.
    """
    _safe_heartbeat("Resolving situation")
    log.info("resolve_situation: situation_id=%s", situation.get("id", ""))

    recovery = situation.get("recovery") or {}
    if recovery.get("verified") is not True:
        log.warning(
            "resolve_situation: refusing to mark %s resolved without a verified "
            "recovery", situation.get("id", ""),
        )
        return {
            **situation,
            "status": situation.get("status", "INVESTIGATING"),
            "resolution_refused": True,
            "reason": (
                "no_verified_recovery: a situation is only resolved behind a "
                "verified recovery outcome"
            ),
        }

    return {
        **situation,
        "status": "RESOLVED",
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Activity 9: escalate_situation
# ---------------------------------------------------------------------------


@activity.defn(name="escalate_situation")
async def escalate_situation(situation: dict[str, Any]) -> dict[str, Any]:
    """Escalate the situation when recovery fails."""
    _safe_heartbeat("Escalating situation")
    log.info("escalate_situation: situation_id=%s", situation.get("id", ""))

    # Update status — in production this triggers the escalation ladder
    return {
        **situation,
        "status": "INVESTIGATING",
        "escalated": True,
        "escalated_at": datetime.now(timezone.utc).isoformat(),
    }
