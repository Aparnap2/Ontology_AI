"""Nyayadish — Agent Conflict Arbiter.

Per Kautilyan architecture: the Chief Justice resolves disputes
between Amatyas (guardians) when their findings contradict.

This is a deterministic arbiter using confidence-weighted resolution.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

_SEVERITY_ORDER: dict[str, int] = {
    "critical": 3,
    "warning": 2,
    "info": 1,
}


@dataclass
class ArbitrationResult:
    """Result of inter-agent arbitration."""
    needs_arbitration: bool
    conflict_type: str | None = None
    agents_involved: list[str] = field(default_factory=list)
    resolved_severity: str = "info"
    resolved_action: str = ""
    explanation: str = ""
    confidence: float = 1.0


class ConflictResolver:
    """Arbiter for inter-agent conflicts.

    Detects and resolves contradictions:
    1. Severity mismatch — one says "critical", another says "info"
    2. Signal contradiction — contradictory signals across domains
    """

    def arbitrate(self, guardian_outputs: list[dict]) -> ArbitrationResult:
        """Review guardian outputs for contradictions.

        Only arbitrates when 2+ guardians fire in the same session.

        Args:
            guardian_outputs: List of guardian output dicts, each with:
                - agent: str
                - alert: dict with severity (info/warning/critical)
                - triggered_patterns: list[str]

        Returns:
            ArbitrationResult with resolution
        """
        if not guardian_outputs or len(guardian_outputs) < 2:
            return ArbitrationResult(needs_arbitration=False)

        agents = [o.get("agent", "unknown") for o in guardian_outputs]

        # Check for severity conflict
        sv_conflict = self._has_severity_conflict(guardian_outputs)

        # Check for signal conflict
        sg_conflict = self._has_signal_conflict(guardian_outputs)

        if not sv_conflict and not sg_conflict:
            return ArbitrationResult(needs_arbitration=False)

        # Determine conflict type
        if sv_conflict and sg_conflict:
            conflict_type = "severity_mismatch+signal_contradiction"
        elif sv_conflict:
            conflict_type = "severity_mismatch"
        else:
            conflict_type = "signal_contradiction"

        # Resolve
        resolved_severity = self._resolve_severity(guardian_outputs)
        resolved_action = self._build_resolved_action(
            guardian_outputs, conflict_type, resolved_severity,
        )
        explanation = self._build_explanation(
            guardian_outputs, conflict_type, resolved_severity,
        )

        # Confidence decreases with conflict
        confidence = 0.7 if sv_conflict else 0.85

        return ArbitrationResult(
            needs_arbitration=True,
            conflict_type=conflict_type,
            agents_involved=agents,
            resolved_severity=resolved_severity,
            resolved_action=resolved_action,
            explanation=explanation,
            confidence=confidence,
        )

    def _has_severity_conflict(self, outputs: list[dict]) -> bool:
        """Check if guardians disagree on severity.

        Conflict if: one says "critical" while another says "info"
        """
        severities = {o.get("alert", {}).get("severity", "info") for o in outputs}
        return "critical" in severities and "info" in severities

    def _has_signal_conflict(self, outputs: list[dict]) -> bool:
        """Check if guardians have contradictory signals.

        Rules:
        - Finance "burn_alert" + BI "mrr_trend=growing" → growth-stage tension
          (not a conflict, so returns False)
        - Ops "error_spike" + BI "mrr_trend=declining" → consistent
          (errors → churn, so returns False)
        - Finance "burn_alert" + Ops "no churn_risk_users" → potential conflict
          (high burn should affect operations)
        """
        patterns = self._group_patterns_by_agent(outputs)

        finance_patterns = " ".join(patterns.get("Finance Guardian", [])).lower()
        ops_patterns = " ".join(patterns.get("Ops Guardian", [])).lower()

        # Finance says burn but Ops shows no operational concern → conflict
        has_burn = "burn" in finance_patterns or "burn_alert" in finance_patterns
        has_ops_churn = "churn" in ops_patterns
        has_ops_errors = "error" in ops_patterns or "error_spike" in ops_patterns

        # Only flag when both Finance and Ops are firing
        if has_burn and ops_patterns and not has_ops_churn and not has_ops_errors:
            return True

        return False

    def _resolve_severity(self, outputs: list[dict]) -> str:
        """Resolve severity conflicts.

        Rule: Highest severity wins (critical > warning > info)
        But: If majority disagree with highest, use warning.
        """
        severities = [o.get("alert", {}).get("severity", "info") for o in outputs]
        if not severities:
            return "info"

        # Find highest severity
        ordered = sorted(
            severities,
            key=lambda s: _SEVERITY_ORDER.get(s, 1),
            reverse=True,
        )
        highest = ordered[0]

        # Check if majority disagrees with highest
        count_highest = sum(1 for s in severities if s == highest)
        count_others = len(severities) - count_highest

        if count_others > count_highest:
            return "warning"  # compromise on warning

        return highest

    def _build_resolved_action(
        self,
        outputs: list[dict],
        conflict_type: str,
        resolved_severity: str,
    ) -> str:
        """Build a recommended action based on resolved conflict."""
        if conflict_type == "severity_mismatch":
            # The agents disagree on how bad it is
            if resolved_severity == "critical":
                return "Investigate with highest priority — severity consensus is critical"
            if resolved_severity == "warning":
                return "Escalate for human review — agents disagree on severity"
            return "Monitor — agents disagree but severity is low"

        if conflict_type == "signal_contradiction":
            return "Reconcile contradictory signals across domains"

        if "severity_mismatch" in conflict_type and "signal" in conflict_type:
            return "Escalate for human review — multiple contradictions detected"

        return "Continue monitoring"

    def _build_explanation(
        self,
        outputs: list[dict],
        conflict_type: str,
        resolved_severity: str,
    ) -> str:
        """Build human-readable explanation of the conflict."""
        agents = [o.get("agent", "unknown") for o in outputs]
        agent_list = ", ".join(agents)

        parts: list[str] = [f"Conflict between: {agent_list}"]

        if "severity_mismatch" in conflict_type:
            severities = {
                o.get("agent", "?"): o.get("alert", {}).get("severity", "?")
                for o in outputs
            }
            parts.append(f"Severity disagreement: {severities}")
            parts.append(f"Resolved severity: {resolved_severity}")

        if "signal" in conflict_type:
            parts.append("Contradictory signals detected across domains")

        return " | ".join(parts)

    def _group_patterns_by_agent(self, outputs: list[dict]) -> dict[str, list[str]]:
        """Group triggered_patterns by agent name."""
        result: dict[str, list[str]] = {}
        for o in outputs:
            agent = o.get("agent", "unknown")
            result[agent] = o.get("triggered_patterns", [])
        return result
