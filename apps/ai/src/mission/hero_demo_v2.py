"""Hero Demo V2 — 9-scene structured timeline for the 02:13 incident.

Produces a deterministic, rich-output demo suitable for a 5-10 minute
portfolio walkthrough. Each scene is a ``DemoScene`` with narrative,
evidence, decision, and audience-facing context.

All inputs are deterministic. No real LLM, no real network, no I/O.

Usage::

    scenes = run_full_demo()
    for scene in scenes:
        print(scene.model_dump_json(indent=2))
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

DEMO_TENANT: str = "t-acme"
DEMO_MISSION: str = "m-hero-v2"
DEMO_INCIDENT_ID: str = "inc-pay-hero-v2"
DEMO_VENDOR_ID: str = "stripe"
DEMO_SLA_ID: str = "sla-pay-hero-v2"
DEMO_SERVICE_ID: str = "svc-payments-v2"

# ── Models ───────────────────────────────────────────────────────────────


class DemoScene(BaseModel):
    """A single scene in the hero demo timeline.

    Each scene captures the full state transition: what came in,
    what the system produced, and why it matters to the audience.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    scene_number: int = Field(ge=1, le=9)
    title: str
    timestamp: str
    input_state: dict[str, Any]
    output_state: dict[str, Any]
    narrative: str
    evidence: list[str]
    decision: str
    why_it_matters: str


class DemoOutput(BaseModel):
    """Complete output of the 9-scene hero demo run."""

    model_config = ConfigDict(extra="forbid", strict=True)

    demo_id: str
    tenant: str
    scenes: list[DemoScene]


# ── Scene builders (deterministic, pure functions) ──────────────────────


def _scene_1_incident_arrives() -> DemoScene:
    """Scene 1 — A production incident arrives from external monitoring."""
    return DemoScene(
        scene_number=1,
        title="Incident arrives",
        timestamp="2026-09-12T02:13:00Z",
        input_state={
            "source": "monitoring",
            "vendor": "Stripe",
            "severity": "critical",
            "raw_alert": "Payment API returning 503 errors",
        },
        output_state={
            "incident_id": DEMO_INCIDENT_ID,
            "incident_type": "vendor",
            "status": "open",
            "severity": "critical",
        },
        narrative=(
            "A production incident arrives from external monitoring. "
            "The system ingests it immediately."
        ),
        evidence=[
            "Payment API returning 503",
            "Vendor: Stripe",
        ],
        decision="Incident classified as vendor-originated",
        why_it_matters=(
            "Demonstrates real-time event ingestion and classification. "
            "The system knows this is a vendor incident, not an internal failure."
        ),
    )


def _scene_2_ontology_resolution() -> DemoScene:
    """Scene 2 — The ontology resolves the incident to its business impact chain."""
    return DemoScene(
        scene_number=2,
        title="Ontology resolution",
        timestamp="2026-09-12T02:13:02Z",
        input_state={
            "incident_id": DEMO_INCIDENT_ID,
            "incident_type": "vendor",
        },
        output_state={
            "impact_chain": [
                "Incident",
                "Payment API",
                "Checkout",
                "Payment Process",
                "PayCore",
            ],
            "business_impact": "checkout flow degraded",
        },
        narrative=(
            "The ontology resolves the incident to its business impact chain. "
            "This is not a prompt — it is structured domain reasoning."
        ),
        evidence=[
            "Incident → Payment API → Checkout → Payment Process → PayCore",
        ],
        decision="Business impact: checkout flow degraded",
        why_it_matters=(
            "Shows why ontology matters — not just an LLM call, "
            "but structured domain reasoning that maps technical incidents "
            "to business consequences."
        ),
    )


def _scene_3_sla_clock_starts() -> DemoScene:
    """Scene 3 — SLA tracking begins immediately with escalation schedule."""
    return DemoScene(
        scene_number=3,
        title="SLA clock starts",
        timestamp="2026-09-12T02:13:03Z",
        input_state={
            "incident_id": DEMO_INCIDENT_ID,
            "severity": "critical",
        },
        output_state={
            "sla_id": DEMO_SLA_ID,
            "sla_tier": "P1",
            "ack_deadline_minutes": 15,
            "resolution_deadline_minutes": 60,
            "escalation_schedule": ["T0", "T1", "T2"],
        },
        narrative=(
            "SLA tracking begins immediately. The system knows the "
            "escalation ladder and the deadlines."
        ),
        evidence=[
            "P1 SLA: 15min response, 1hr resolution",
            "Escalation: T0→T1→T2",
        ],
        decision="SLA clock running, next check in 15 minutes",
        why_it_matters=(
            "Demonstrates temporal awareness and proactive escalation. "
            "The system does not wait for a human to set a timer."
        ),
    )


def _scene_4_agent_investigation() -> DemoScene:
    """Scene 4 — The agent investigates using the checkpoint, not the raw event."""
    return DemoScene(
        scene_number=4,
        title="Agent investigation",
        timestamp="2026-09-12T02:13:08Z",
        input_state={
            "incident_id": DEMO_INCIDENT_ID,
            "evidence": "monitoring data, vendor status, historical patterns",
            "checkpoint": f"cp-{DEMO_MISSION}",
        },
        output_state={
            "action_intent": {
                "operation": "vendor_ticket.create",
                "parameters": {
                    "vendor_id": DEMO_VENDOR_ID,
                    "incident_id": DEMO_INCIDENT_ID,
                    "title": "Payment gateway 503 — escalate",
                },
                "confidence": 0.88,
                "risk_tier": "MEDIUM",
            },
        },
        narrative=(
            "The agent investigates using the checkpoint, not just the raw event. "
            "It emits an intent — it does not execute an action."
        ),
        evidence=[
            "Evidence: monitoring data, vendor status, historical patterns",
        ],
        decision="Intent: create vendor ticket for payment API investigation",
        why_it_matters=(
            "Shows the LLM's actual role: emit intent, not execute actions. "
            "The agent proposes; the control plane decides."
        ),
    )


def _scene_5_control_plane_gate() -> DemoScene:
    """Scene 5 — The control plane validates authorization, safety, idempotency."""
    return DemoScene(
        scene_number=5,
        title="Control plane gate",
        timestamp="2026-09-12T02:13:09Z",
        input_state={
            "action_intent": {
                "operation": "vendor_ticket.create",
                "confidence": 0.88,
                "risk_tier": "MEDIUM",
            },
        },
        output_state={
            "authorization": "pass",
            "policy_check": "pass",
            "idempotency": "new",
            "authorized_action": {
                "operation": "vendor_ticket.create",
                "status": "authorized",
            },
        },
        narrative=(
            "The control plane validates: is this authorized, safe, idempotent? "
            "Every action must pass the governance gate."
        ),
        evidence=[
            "Authorization: pass",
            "Policy: pass",
            "Idempotency: new",
        ],
        decision="Authorized for execution",
        why_it_matters=(
            "This is the core differentiator: LLM proposes, infrastructure decides. "
            "The system enforces governance before any side effect."
        ),
    )


def _scene_6_vendor_interaction() -> DemoScene:
    """Scene 6 — The system executes the authorized action against the vendor."""
    return DemoScene(
        scene_number=6,
        title="Vendor interaction",
        timestamp="2026-09-12T02:13:10Z",
        input_state={
            "authorized_action": {
                "operation": "vendor_ticket.create",
                "status": "authorized",
            },
        },
        output_state={
            "ticket_id": "VT-2024-001",
            "vendor": "Stripe",
            "status": "open",
            "external_api_call": "POST /v1/tickets",
        },
        narrative=(
            "The system executes the authorized action against the vendor. "
            "A real ticket is created."
        ),
        evidence=[
            "POST to vendor ticket API",
            "Ticket ID: VT-2024-001",
        ],
        decision="Vendor ticket created successfully",
        why_it_matters=(
            "Proves real external side effects, not just planning. "
            "The system acts on its decisions."
        ),
    )


def _scene_7_false_recovery_detection() -> DemoScene:
    """Scene 7 — Vendor claims resolved, but evidence does not support it."""
    return DemoScene(
        scene_number=7,
        title="False recovery detection",
        timestamp="2026-09-12T02:25:00Z",
        input_state={
            "vendor_claim": "RESOLVED",
            "monitoring": "STILL FAILING",
            "checkout_status": "STILL DEGRADED",
        },
        output_state={
            "recovery_verified": False,
            "error_rate": 0.35,
            "success_rate": 0.65,
            "mismatches": ["error_rate", "success_rate"],
        },
        narrative=(
            "The vendor claims resolution, but the evidence doesn't support it. "
            "The system rejects the false recovery."
        ),
        evidence=[
            "Vendor claim: RESOLVED",
            "Monitoring: STILL FAILING",
            "Checkout: STILL DEGRADED",
        ],
        decision="Recovery verification FAILED — mission continues",
        why_it_matters=(
            "Best moment in the demo: system rejects false recovery based on evidence. "
            "It trusts data, not vendor claims."
        ),
    )


def _scene_8_escalation() -> DemoScene:
    """Scene 8 — SLA threshold reached, system escalates per policy."""
    return DemoScene(
        scene_number=8,
        title="Escalation",
        timestamp="2026-09-12T02:28:00Z",
        input_state={
            "sla_tier": "P1",
            "current_tier": "T1",
            "ack_deadline_reached": True,
        },
        output_state={
            "escalation_level": "L4",
            "escalation_target": "human_notification",
            "notification_sent": True,
        },
        narrative=(
            "SLA threshold reached. The system escalates per policy. "
            "No human needed to trigger it."
        ),
        evidence=[
            "T1 threshold reached",
            "Escalating to L4",
        ],
        decision="Escalation: L4 — human notification",
        why_it_matters=(
            "Shows temporal escalation working as designed. "
            "The system escalates automatically when thresholds are breached."
        ),
    )


def _scene_9_verified_recovery() -> DemoScene:
    """Scene 9 — Real recovery confirmed by evidence. Mission complete."""
    return DemoScene(
        scene_number=9,
        title="Verified recovery",
        timestamp="2026-09-12T02:45:00Z",
        input_state={
            "monitoring": "HEALTHY",
            "checkout_status": "HEALTHY",
            "vendor_status": "RESOLVED",
        },
        output_state={
            "recovery_verified": True,
            "error_rate": 0.0,
            "success_rate": 1.0,
            "mission_status": "resolved",
        },
        narrative=(
            "Real recovery confirmed by evidence. Mission complete. "
            "The full loop is closed."
        ),
        evidence=[
            "Monitoring: HEALTHY",
            "Checkout: HEALTHY",
            "Vendor: RESOLVED",
        ],
        decision="Recovery VERIFIED — mission RESOLVED",
        why_it_matters=(
            "Full loop closed: incident → investigation → action → "
            "verification → resolution. The system delivers end-to-end."
        ),
    )


# ── Public API ───────────────────────────────────────────────────────────

_SCENE_BUILDERS = [
    _scene_1_incident_arrives,
    _scene_2_ontology_resolution,
    _scene_3_sla_clock_starts,
    _scene_4_agent_investigation,
    _scene_5_control_plane_gate,
    _scene_6_vendor_interaction,
    _scene_7_false_recovery_detection,
    _scene_8_escalation,
    _scene_9_verified_recovery,
]


def build_all_scenes() -> list[DemoScene]:
    """Build all 9 demo scenes in order.

    Returns
    -------
    list[DemoScene]
        The complete 9-scene timeline.
    """
    return [builder() for builder in _SCENE_BUILDERS]


def run_full_demo() -> DemoOutput:
    """Run the full 9-scene hero demo.

    Returns
    -------
    DemoOutput
        Structured output containing all 9 scenes with metadata.
    """
    scenes = build_all_scenes()
    output = DemoOutput(
        demo_id=DEMO_MISSION,
        tenant=DEMO_TENANT,
        scenes=scenes,
    )
    logger.info("Hero demo v2 complete: %d scenes", len(scenes))
    return output


def scenes_to_json(output: DemoOutput, *, indent: int = 2) -> str:
    """Serialize the demo output to JSON.

    Parameters
    ----------
    output:
        The demo output to serialize.
    indent:
        JSON indentation level.

    Returns
    -------
    str
        JSON string of the demo output.
    """
    return output.model_dump_json(indent=indent)


def scenes_to_dict_list(scenes: list[DemoScene]) -> list[dict[str, Any]]:
    """Convert scenes to a list of plain dicts.

    Parameters
    ----------
    scenes:
        List of DemoScene objects.

    Returns
    -------
    list[dict[str, Any]]
        Each scene as a plain dictionary.
    """
    return [scene.model_dump() for scene in scenes]
