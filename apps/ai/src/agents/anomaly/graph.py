"""Charaka — Cross-Domain Anomaly Checker (Wandering Spy).

Per Kautilyan architecture: the Charaka roams across all departments
looking for inconsistencies between what different officers report.

This is a deterministic consistency checker — no LLM calls.

Also retains backward-compatible stub functions anomaly_graph()
and build_anomaly_graph() for existing imports.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnomalyAlert:
    """Alert produced by the Charaka cross-domain check."""
    should_alert: bool
    inconsistency_type: str | None = None
    domains: list[str] = field(default_factory=list)
    description: str = ""
    severity: str = "info"


class AnomalyDetector:
    """Cross-domain inconsistency detector.

    Checks across MissionState fields for contradictory signals:
    1. Finance says burn is high but Ops shows no operational issues
    2. BI shows strong growth but Finance shows cash declining fast
    3. Ops shows error spike but BI shows normal user behavior
    4. Runway critical but founder focused elsewhere
    """

    def check(self, mission_state: dict) -> AnomalyAlert:
        """Run cross-domain consistency checks.

        Check 1: burn_alert AND (no churn_risk_users AND no error_spike)
            → Inconsistency: Finance says burn critical but operations normal
            → severity: warning

        Check 2: mrr_trend == "growing" AND burn_alert
            → Inconsistency: Revenue growing but cash burning fast
            → severity: warning (growth-stage tension)

        Check 3: error_spike AND mrr_trend in ("stable", "growing")
            → Inconsistency: Ops says errors but BI shows normal usage
            → severity: info (could be unrelated)

        Check 4: runway_days AND runway_days < 90 AND founder_focus != "fundraising"
            → Inconsistency: Runway critical but founder focused elsewhere
            → severity: critical

        Args:
            mission_state: Dict with keys: burn_alert, churn_risk_users, error_spike,
                          mrr_trend, runway_days, founder_focus, etc.

        Returns:
            AnomalyAlert — should_alert=False if no inconsistencies found
        """
        if not mission_state:
            return AnomalyAlert(should_alert=False)

        # Run all checks in order; return the first one found
        # (since each is an actionable inconsistency)

        # Check 1: High burn without operational symptoms
        found, desc = self._check_burn_without_ops_impact(mission_state)
        if found:
            return AnomalyAlert(
                should_alert=True,
                inconsistency_type="finance_ops_mismatch",
                domains=["finance", "ops"],
                description=desc,
                severity="warning",
            )

        # Check 2: Revenue growing but cash burning
        found, desc = self._check_growth_with_burn(mission_state)
        if found:
            return AnomalyAlert(
                should_alert=True,
                inconsistency_type="bi_finance_conflict",
                domains=["bi", "finance"],
                description=desc,
                severity="warning",
            )

        # Check 3: Error spike without user impact
        found, desc = self._check_errors_with_normal_usage(mission_state)
        if found:
            return AnomalyAlert(
                should_alert=True,
                inconsistency_type="ops_bi_divergence",
                domains=["ops", "bi"],
                description=desc,
                severity="info",
            )

        # Check 4: Short runway but founder not focused on it
        found, desc = self._check_runway_mismatch(mission_state)
        if found:
            return AnomalyAlert(
                should_alert=True,
                inconsistency_type="runway_founder_mismatch",
                domains=["finance", "ops", "bi"],
                description=desc,
                severity="critical",
            )

        return AnomalyAlert(should_alert=False)

    def _check_burn_without_ops_impact(self, ms: dict) -> tuple[bool, str]:
        """Check 1: High burn without operational symptoms.

        Finance reports burn_alert but Ops shows no churn risk users
        and no error spikes. This is an inconsistency because high
        burn should manifest in operational metrics.
        """
        burn_alert = ms.get("burn_alert", False)
        churn_risk = ms.get("churn_risk_users", 0)
        error_spike = ms.get("error_spike", False)

        if burn_alert and not churn_risk and not error_spike:
            return True, (
                "Finance reports high burn rate but operations show "
                "no churn risk users and no error spikes. "
                "Either the burn is not impacting operations yet, "
                "or there's a reporting inconsistency."
            )
        return False, ""

    def _check_growth_with_burn(self, ms: dict) -> tuple[bool, str]:
        """Check 2: Revenue growing but cash burning.

        BI shows mrr_trend=growing but Finance reports burn_alert.
        This is a growth-stage tension — typical for startups
        investing aggressively in growth.
        """
        mrr_trend = ms.get("mrr_trend", "")
        burn_alert = ms.get("burn_alert", False)

        if mrr_trend == "growing" and burn_alert:
            return True, (
                "Revenue is growing (MRR trend: growing) but cash is "
                "burning fast. This is common growth-stage tension — "
                "investing in growth at the cost of cash reserves."
            )
        return False, ""

    def _check_errors_with_normal_usage(self, ms: dict) -> tuple[bool, str]:
        """Check 3: Error spike without user impact.

        Ops shows error_spike but BI shows normal usage (mrr_trend
        is stable or growing). The errors may be isolated and not
        affecting the user-facing experience.
        """
        error_spike = ms.get("error_spike", False)
        mrr_trend = ms.get("mrr_trend", "")

        if error_spike and mrr_trend in ("stable", "growing"):
            return True, (
                "Operations reports an error spike but user-facing metrics "
                f"(MRR trend: {mrr_trend}) remain normal. "
                "The errors may be isolated to non-critical paths."
            )
        return False, ""

    def _check_runway_mismatch(self, ms: dict) -> tuple[bool, str]:
        """Check 4: Short runway but founder not focused on fundraising.

        If runway_days < 90 and founder_focus is on anything other
        than fundraising, this is a critical misalignment.
        """
        runway_days = ms.get("runway_days")
        founder_focus = ms.get("founder_focus", "")

        if runway_days is not None and runway_days < 90:
            if founder_focus and founder_focus != "fundraising":
                return True, (
                    f"Runway is critically short ({runway_days} days) but "
                    f"founder is focused on '{founder_focus}' instead of "
                    "fundraising. This is a critical misalignment that "
                    "needs immediate attention."
                )
        return False, ""


# ── Backward-compatible stub functions ───────────────────────────────────


def anomaly_graph(tenant_id: str) -> dict:
    """Backward-compatible stub — returns basic tenant info.

    For full cross-domain anomaly detection, use AnomalyDetector.check().
    """
    return {"tenant_id": tenant_id}


def build_anomaly_graph(tenant_id: str) -> Any:
    """Backward-compatible wrapper for anomaly_graph()."""
    return anomaly_graph(tenant_id)
