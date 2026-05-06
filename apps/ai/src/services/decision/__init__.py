"""
Decision Engine Service - Combines Guardian Watchlist + HITL Routing
"""
from datetime import datetime
from typing import Optional

from .schemas import DecisionRequest, DecisionResult, Severity, PatternMatch


class DecisionService:
    """
    Decision Engine wraps guardian watchlist evaluation and HITL routing.
    Uses existing guardian.detector and hitl.manager from src/.
    """

    def __init__(self):
        self._guardian = None
        self._hitl_manager = None

    def _get_guardian(self):
        """Lazy load guardian detector."""
        if self._guardian is None:
            try:
                from apps.ai.src.guardian.detector import GuardianDetector
                self._guardian = GuardianDetector()
            except ImportError:
                pass
        return self._guardian

    def _get_hitl_manager(self):
        """Lazy load HITL manager."""
        if self._hitl_manager is None:
            try:
                from apps.ai.src.hitl.manager import HITLManager
                self._hitl_manager = HITLManager()
            except ImportError:
                pass
        return self._hitl_manager

    def evaluate(self, tenant_id: str, signals: dict) -> DecisionResult:
        """
        Evaluate signals against guardian watchlist.
        
        Args:
            tenant_id: Tenant identifier
            signals: Dict of computed metrics/signals
            
        Returns:
            DecisionResult with should_alert, severity, confidence, hitl_required
        """
        # Run guardian detection
        guardian = self._get_guardian()
        hitl_manager = self._get_hitl_manager()

        # Run guardian detection
        if guardian:
            matches = guardian.run(signals)
            pattern_name = matches[0].id if matches else None
            severity_str = matches[0].severity if matches else "info"
            severity = Severity(severity_str) if severity_str in ["critical", "warning", "info"] else Severity.INFO
            confidence = 0.85 if matches else 0.5
        else:
            pattern_name = self._detect_pattern(signals)
            severity = self._detect_severity(signals)
            confidence = 0.75

        should_alert = pattern_name is not None

        # Determine HITL requirement
        hitl_required = False
        if hitl_manager and should_alert:
            is_investor_update = signals.get("is_investor_update", False)
            routing = hitl_manager.route(
                severity=severity.value,
                confidence=confidence,
                is_new_pattern=False,
                is_investor_update=is_investor_update
            )
            hitl_required = routing in ["approve", "review"]
        elif severity == Severity.CRITICAL and confidence < 0.6:
            hitl_required = True

        # Generate insight
        insight = self._generate_insight(pattern_name, signals)

        return DecisionResult(
            tenant_id=tenant_id,
            should_alert=should_alert,
            severity=severity,
            pattern_name=pattern_name,
            insight=insight,
            confidence=confidence,
            hitl_required=hitl_required
        )

    def _detect_pattern(self, signals: dict) -> Optional[str]:
        """Fallback pattern detection without guardian."""
        if signals.get("monthly_churn_pct", 0) > 0.03:
            return "FG-01"
        if signals.get("burn_multiple", 0) > 2.0:
            return "FG-02"
        if signals.get("activation_rate", 1) < 0.2:
            return "BG-01"
        if signals.get("deploy_frequency", 0) < 1:
            return "OG-01"
        return None

    def _detect_severity(self, signals: dict) -> Severity:
        """Detect severity from signals."""
        if signals.get("monthly_churn_pct", 0) > 0.05:
            return Severity.CRITICAL
        if signals.get("runway_months", 999) < 6:
            return Severity.CRITICAL
        if signals.get("burn_multiple", 0) > 2.5:
            return Severity.CRITICAL
        return Severity.WARNING

    def _generate_insight(self, pattern_name: Optional[str], signals: dict) -> str:
        """Generate human-readable insight."""
        if not pattern_name:
            return "No patterns detected. Metrics within normal ranges."

        insights = {
            "FG-01": f"Monthly churn at {signals.get('monthly_churn_pct', 0)*100:.1f}% exceeds 3% threshold",
            "FG-02": f"Burn multiple of {signals.get('burn_multiple', 0):.1f}x exceeds 2x threshold",
            "BG-01": f"Activation rate at {signals.get('activation_rate', 0)*100:.1f}% below 20% wall",
            "OG-01": f"Deploy frequency of {signals.get('deploy_frequency', 0)}/week below 1/week",
        }
        return insights.get(pattern_name, f"Pattern {pattern_name} detected")

    async def publish_result(self, result: DecisionResult) -> bool:
        """Publish decision result to Redpanda."""
        try:
            from apps.ai.src.events.redpanda import publish_guardian_result
            return await publish_guardian_result(
                tenant_id=result.tenant_id,
                alert_id=result.decision_id,
                decision="APPROVED" if result.should_alert else "DISMISSED",
                message=result.insight
            )
        except ImportError:
            return False