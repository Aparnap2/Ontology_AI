"""ROI Measurement — deterministic savings calculation for governed incidents.

Compares the AI-governed incident response against a manual-process baseline.
All inputs are caller-supplied (injected ``now``, no wall clock, no LLM).

The demo scenario uses this to prove measurable value from the platform.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class ROIMetrics(BaseModel):
    """Raw ROI measurements tied to a single incident response.

    All time values are in minutes.  ``total_cost_usd`` is the estimated
    cost of downtime during the incident window.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    time_to_detect_minutes: float = Field(ge=0.0)
    time_to_acknowledge_minutes: float = Field(ge=0.0)
    time_to_resolve_minutes: float = Field(ge=0.0)
    sla_compliance: bool
    escalation_count: int = Field(ge=0)
    vendor_ticket_created: bool
    recovery_verified: bool
    total_cost_usd: float = Field(ge=0.0)


class ROISavings(BaseModel):
    """Calculated savings from governed vs manual incident response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    time_saved_detect_minutes: float
    time_saved_acknowledge_minutes: float
    time_saved_resolve_minutes: float
    escalation_reduction: int
    cost_saved_usd: float
    sla_met_improvement: bool
    recovery_verified_improvement: bool
    total_savings_usd: float = Field(ge=0.0)


# ── Cost model (deterministic, injectable) ──────────────────────────────

#: Cost per minute of downtime (configurable for different businesses).
DOWNTIME_COST_PER_MINUTE: float = 50.0

#: Estimated cost per escalation (human time, coordination overhead).
ESCALATION_COST_USD: float = 200.0


def calculate_roi(
    metrics: ROIMetrics,
    baseline: ROIMetrics,
    *,
    downtime_cost_per_minute: float = DOWNTIME_COST_PER_MINUTE,
    escalation_cost_usd: float = ESCALATION_COST_USD,
) -> ROISavings:
    """Calculate savings vs baseline (manual process).

    Savings come from four sources:
    1. Faster detection (fewer minutes of undetected downtime).
    2. Faster acknowledgement (SLA met earlier).
    3. Faster resolution (shorter total incident window).
    4. Fewer escalations (less human coordination overhead).

    All arithmetic is pure; no wall clock, no LLM, no I/O.
    """
    time_saved_detect = max(
        0.0, baseline.time_to_detect_minutes - metrics.time_to_detect_minutes
    )
    time_saved_ack = max(
        0.0, baseline.time_to_acknowledge_minutes - metrics.time_to_acknowledge_minutes
    )
    time_saved_resolve = max(
        0.0, baseline.time_to_resolve_minutes - metrics.time_to_resolve_minutes
    )
    escalation_reduction = max(0, baseline.escalation_count - metrics.escalation_count)

    # Cost savings: downtime cost reduction + escalation cost reduction
    downtime_savings = time_saved_resolve * downtime_cost_per_minute
    escalation_savings = escalation_reduction * escalation_cost_usd
    total_savings = downtime_savings + escalation_savings

    return ROISavings(
        time_saved_detect_minutes=time_saved_detect,
        time_saved_acknowledge_minutes=time_saved_ack,
        time_saved_resolve_minutes=time_saved_resolve,
        escalation_reduction=escalation_reduction,
        cost_saved_usd=downtime_savings,
        sla_met_improvement=(not baseline.sla_compliance and metrics.sla_compliance),
        recovery_verified_improvement=(
            not baseline.recovery_verified and metrics.recovery_verified
        ),
        total_savings_usd=total_savings,
    )
