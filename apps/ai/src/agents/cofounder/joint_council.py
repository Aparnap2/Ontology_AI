"""Mantriparishad — Joint Alert Council Synthesizer.

Per Kautilyan architecture: when multiple Amatyas (guardians) fire
in the same session, convene a council to produce one synthesized alert
with unified root cause, cross-domain severity, and one recommended action.

This is stateless — decisions are based only on the current batch of
guardian outputs and MissionState.
"""
from __future__ import annotations
from dataclasses import dataclass, field

# ── Cross-domain keyword detection ──────────────────────────────────────
# Used to determine if a single critical alert has overlapping concern
# across departmental boundaries.
_DOMAIN_KEYWORDS: dict[str, set[str]] = {
    "finance": {
        "burn", "revenue", "cash", "margin", "mrr", "runway",
        "cost", "spend", "budget", "ebitda", "profit", "loss",
    },
    "ops": {
        "error", "deploy", "latency", "downtime", "infrastructure",
        "outage", "response_time", "p99", "incident", "reliability",
    },
    "bi": {
        "growth", "user", "churn", "engagement", "trend",
        "retention", "acquisition", "usage", "active", "conversion",
    },
}


@dataclass
class AlertCouncilResult:
    """Synthesized output from the joint council."""
    should_synthesize: bool
    root_cause: str = ""
    severity: str = "info"
    domains_involved: list[str] = field(default_factory=list)
    recommended_action: str = ""
    individual_alerts: list[dict] = field(default_factory=list)
    confidence: float = 0.0


# ── Agent-to-domain mapping ─────────────────────────────────────────────
_AGENT_DOMAIN_MAP: dict[str, str] = {
    "Finance Guardian": "finance",
    "BI Guardian": "bi",
    "Ops Guardian": "ops",
    "finance": "finance",
    "bi": "bi",
    "ops": "ops",
}


def _extract_domains(outputs: list[dict]) -> set[str]:
    """Extract unique domain names from guardian outputs."""
    domains: set[str] = set()
    for o in outputs:
        agent_name = o.get("agent", "")
        domain = _AGENT_DOMAIN_MAP.get(agent_name, agent_name.lower().replace(" ", "_"))
        domains.add(domain)
    return domains


def _has_overlapping_concern(patterns: list[str]) -> bool:
    """Check if triggered patterns span cross-domain concerns.

    Returns True if the pattern keywords match 2+ domain keyword sets,
    indicating the alert affects multiple departments even though
    only one guardian fired.
    """
    if not patterns:
        return False
    pattern_text = " ".join(patterns).lower()
    domains_with_matches: set[str] = set()
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in pattern_text:
                domains_with_matches.add(domain)
                break
    return len(domains_with_matches) >= 2


def _infer_severity(outputs: list[dict]) -> str:
    """Infer overall severity from multiple guardian outputs.

    - Any "critical" → severity = "critical"
    - 2+ "warning" → severity = "warning"
    - 1 "warning" → severity = "warning"
    - All "info" → severity = "info"
    """
    severities = [o.get("alert", {}).get("severity", "info") for o in outputs]

    if any(s == "critical" for s in severities):
        return "critical"
    if any(s == "warning" for s in severities):
        return "warning"
    return "info"


def _build_root_cause(outputs: list[dict], mission_state: dict | None = None) -> str:
    """Build a human-readable root cause from multiple outputs.

    Format: "Cross-domain alert: <domain1> + <domain2>"

    If a mission_state with founder_focus exists, use that as context.
    """
    domains = sorted(_extract_domains(outputs))
    domain_str = " + ".join(d for d in domains if d)

    cause = f"Cross-domain alert: {domain_str}"

    if mission_state and mission_state.get("founder_focus"):
        cause = f"{cause} (founder context: {mission_state['founder_focus']})"

    return cause


def _extract_recommended_action(outputs: list[dict], overall_severity: str) -> str:
    """Extract best recommended action from guardian outputs.

    For critical: combine actions from all critical guardians.
    For warning: use the first guardian's action.
    For info: general monitoring recommendation.
    """
    if overall_severity == "critical":
        actions: list[str] = []
        for o in outputs:
            alert = o.get("alert", {})
            if alert.get("severity") == "critical" and alert.get("primary_signal"):
                actions.append(f"Review {alert['primary_signal']}")
        if actions:
            return "; ".join(actions[:3])  # max 3 actions
        return "Convene emergency cross-domain review"

    if overall_severity == "warning":
        for o in outputs:
            alert = o.get("alert", {})
            if alert.get("primary_signal"):
                return f"Monitor {alert['primary_signal']} across domains"
        return "Monitor cross-domain signals"

    return "Continue monitoring — no immediate action required"


class AlertCouncil:
    """Joint council for cross-domain alert synthesis.

    Per Kautilyan design:
    - Mantri (Chief Minister) presides over the council
    - Multiple Amatyas (guardians) present their findings
    - Council synthesizes before the Swami (founder) acts
    """

    def synthesize(
        self,
        guardian_outputs: list[dict],
        mission_state: dict | None = None,
    ) -> AlertCouncilResult:
        """Determine if council synthesis is needed and produce unified alert.

        Rules:
        1. If 2+ guardians fire within the same session → synthesize
        2. If 1 guardian fires with critical severity AND overlapping concern → synthesize
        3. Otherwise → don't synthesize (let individual alerts through)

        Args:
            guardian_outputs: List of guardian outputs, each with:
                - agent: str (e.g. "Finance Guardian")
                - alert: dict with severity, primary_signal
                - triggered_patterns: list[str]
            mission_state: Optional MissionState dict for additional context

        Returns:
            CouncilAlert with synthesis decision
        """
        if not guardian_outputs:
            return AlertCouncilResult(should_synthesize=False)

        # Rule 1: 2+ guardians firing → synthesize
        if len(guardian_outputs) >= 2:
            should_synthesize = True
        # Rule 2: 1 guardian with critical + overlapping concern → synthesize
        elif len(guardian_outputs) == 1:
            alert = guardian_outputs[0].get("alert", {})
            severity = alert.get("severity", "info")
            patterns = guardian_outputs[0].get("triggered_patterns", [])
            if severity == "critical" and _has_overlapping_concern(patterns):
                should_synthesize = True
            else:
                should_synthesize = False
        else:
            should_synthesize = False

        if not should_synthesize:
            return AlertCouncilResult(should_synthesize=False)

        # Build the synthesized alert
        severity = _infer_severity(guardian_outputs)
        root_cause = _build_root_cause(guardian_outputs, mission_state)
        recommended_action = _extract_recommended_action(guardian_outputs, severity)

        # Confidence: 2+ guardians = high confidence, single critical = medium
        confidence = 0.85 if len(guardian_outputs) >= 2 else 0.65

        return AlertCouncilResult(
            should_synthesize=True,
            root_cause=root_cause,
            severity=severity,
            domains_involved=sorted(_extract_domains(guardian_outputs)),
            recommended_action=recommended_action,
            individual_alerts=list(guardian_outputs),
            confidence=confidence,
        )
