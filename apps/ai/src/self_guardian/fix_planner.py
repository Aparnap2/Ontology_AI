"""Fix Planner — produces structured remediation proposals from deviations.

Analyzes SelfGuardianAlerts and produces FixProposals with blast
radius classification, reversibility check, and approval routing.
No LLM calls — deterministic rules only.
"""
from __future__ import annotations

import logging
from uuid import uuid4

from src.schemas.self_guardian import (
    BlastRadius,
    DeviationType,
    FixProposal,
    SelfGuardianAlert,
)

log = logging.getLogger(__name__)

# Actions that are always reversible and low-blast-radius
_AUTO_FIX_ACTIONS: set[str] = {
    "rollback_prompt",
    "switch_model",
    "rerun_workflow",
}

# Deviation → default action mapping
_DEVIATION_FIX_MAP: dict[DeviationType, str] = {
    DeviationType.UNAUTHORIZED_TOOL: "disable_tool",
    DeviationType.DATA_CLASSIFICATION_MISMATCH: "notify_operator",
    DeviationType.EXTERNAL_FACING_VIOLATION: "notify_operator",
    DeviationType.STATE_CORRUPTION: "rerun_workflow",
    DeviationType.CONFIDENCE_DROP: "switch_model",
    DeviationType.RATE_LIMIT_EXCEEDED: "pause_schedule",
}


def _classify_blast_radius(alert: SelfGuardianAlert) -> BlastRadius:
    """Classify blast radius based on alert severity and deviation type."""
    if alert.severity == "critical":
        return BlastRadius.HIGH
    if alert.deviation in (
        DeviationType.EXTERNAL_FACING_VIOLATION,
        DeviationType.DATA_CLASSIFICATION_MISMATCH,
    ):
        return BlastRadius.HIGH
    if alert.severity == "warning":
        return BlastRadius.MEDIUM
    return BlastRadius.LOW


def _is_reversible(action: str) -> bool:
    return action in _AUTO_FIX_ACTIONS


def _requires_approval(action: str, blast_radius: BlastRadius, reversible: bool) -> bool:
    """Only auto-apply if blast radius is LOW AND action is reversible."""
    if blast_radius == BlastRadius.LOW and reversible:
        return False
    return True


def plan_fix(alert: SelfGuardianAlert) -> FixProposal:
    """Produce a FixProposal from a SelfGuardianAlert.

    Args:
        alert: The deviation to remediate.

    Returns:
        A FixProposal with typed blast radius, reversibility, and
        approval routing.
    """
    action = _DEVIATION_FIX_MAP.get(alert.deviation, "notify_operator")
    blast_radius = _classify_blast_radius(alert)
    reversible = _is_reversible(action)
    requires_approval = _requires_approval(action, blast_radius, reversible)

    return FixProposal(
        alert_id=str(uuid4()),
        agent_name=alert.observation.agent_name,
        deviation_type=alert.deviation,
        action=action,
        description=(
            f"Proposed fix for {alert.deviation.value} by "
            f"{alert.observation.agent_name}: {action}"
        ),
        blast_radius=blast_radius,
        reversible=reversible,
        requires_approval=requires_approval,
    )


class FixPlanner:
    """Produces structured FixProposals from SelfGuardianAlerts.

    Thread-safe by design — all logic is stateless.
    """

    def plan(self, alert: SelfGuardianAlert) -> FixProposal:
        """Plan a fix for a single deviation alert."""
        return plan_fix(alert)

    def plan_batch(
        self, alerts: list[SelfGuardianAlert]
    ) -> list[FixProposal]:
        """Plan fixes for multiple alerts.

        Deduplicates: if multiple alerts share the same agent + deviation,
        only the first one gets a proposal (subsequent are logged).
        """
        seen: set[tuple[str, DeviationType]] = set()
        proposals: list[FixProposal] = []

        for alert in alerts:
            key = (alert.observation.agent_name, alert.deviation)
            if key in seen:
                log.debug("Skipping duplicate fix for %s/%s", *key)
                continue
            seen.add(key)
            proposals.append(plan_fix(alert))

        return proposals
