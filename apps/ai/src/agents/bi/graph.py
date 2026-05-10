"""
BI Analyst Graph — LangGraph state machine.

Per PRD Section 8: Implements Generator → Reflector → Curator loop.
Phase 1: DATA ASSEMBLY (zero LLM) - pure Python
Phase 2: COGNITIVE DECISION (1 LLM) - Pydantic output
Phase 3: NARRATIVE GENERATION (1 LLM) - bounded 200 words

Per PRD Section 7: Agent persona - BI Analyst watches for:
- BG-01: DAU drop (>20% week-over-week)
- BG-02: MAU stagnation (no growth in 30 days)
- BG-03: Retention collapse (Day-30 < 20%)
- BG-04: Cohort degradation (new cohort worse than previous)
- BG-05: Activation funnel leak (step-1 to step-2 < 30%)
- BG-06: Growth trend reversal (2-month downtrend)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

log = logging.getLogger(__name__)


@dataclass
class BIAnalystState:
    """State for BI Analyst agent.

    Per PRD Section 8: Each employee agent maintains its own state.
    Co-founder agent orchestrates, employees execute.
    """

    tenant_id: str = ""
    triggered_patterns: list[str] = field(default_factory=list)
    metrics_snapshot: dict | None = None
    alert_decision: dict | None = None
    narrative: str = ""
    confidence_score: float = 1.0

    # Per PRD Section 11: Domain fields written to MissionState
    mrr_trend: str = ""  # e.g., "stable", "growing", "declining"
    churn_rate: str = ""  # e.g., "2.5%", "high", "low"


class BIAnalystGraph:
    """LangGraph for BI Analyst.

    Implements Thin LLM, Fat Deterministic Core pattern:
    - Phase 1: Fetch all data (Python)
    - Phase 2: LLM decides if alert (Pydantic)
    - Phase 3: LLM generates narrative (bounded)
    """

    def __init__(self):
        self.state = BIAnalystState()

    async def run(self, tenant_id: str, mission_context: dict) -> BIAnalystState:
        """Run BI Analyst for a tenant.

        Args:
            tenant_id: The tenant to analyze
            mission_context: Current MissionState from shared context

        Returns:
            BIAnalystState with alert if triggered
        """
        log.info(f"Running BI Analyst for tenant: {tenant_id}")

        self.state.tenant_id = tenant_id

        # Phase 1: DATA ASSEMBLY (zero LLM tokens)
        await self._assemble_data(tenant_id, mission_context)

        # Phase 2: COGNITIVE DECISION (1 small LLM call)
        if self.state.triggered_patterns:
            await self._decide_alert(mission_context)

        # Phase 3: NARRATIVE GENERATION (1 LLM call, bounded)
        if self.state.alert_decision and self.state.alert_decision.get("should_alert"):
            await self._generate_narrative()

        return self.state

    async def _assemble_data(self, tenant_id: str, mission_context: dict):
        """Phase 1: Pure Python data assembly. Zero LLM tokens."""
        # TODO: Fetch from PostgreSQL, Mixpanel, Amplitude
        # TODO: Compute DAU, MAU, retention, cohorts, activation
        # TODO: Apply rule-based anomaly detection (if/elif)

        # Mock data - replace with real DB queries
        self.state.metrics_snapshot = {
            "tenant_id": tenant_id,
            "dau": 0,
            "mau": 0,
            "retention_d30": 0.0,
            "activation_rate": 0.0,
            "mrr_trend": "stable",
            "churn_rate": 0.0,
        }

        # Rule-based detection (zero LLM)
        patterns = []
        snapshot = self.state.metrics_snapshot

        # BG-01: DAU drop (>20% week-over-week)
        # BG-02: MAU stagnation (no growth in 30 days)
        # BG-03: Retention collapse (Day-30 < 20%)
        # BG-04: Cohort degradation
        # BG-05: Activation funnel leak
        # BG-06: Growth trend reversal

        dau_drop = snapshot.get("dau_drop_pct", 0)
        if dau_drop > 20:
            patterns.append("BG-01")

        retention = snapshot.get("retention_d30", 0)
        if retention < 0.20:
            patterns.append("BG-03")

        activation = snapshot.get("activation_rate", 100)
        if activation < 30:
            patterns.append("BG-05")

        self.state.triggered_patterns = patterns
        log.info(f"BI Analyst: {len(patterns)} patterns triggered")

        # Per PRD Section 11: Write domain fields to MissionState
        self.state.mrr_trend = snapshot.get("mrr_trend", "stable")
        self.state.churn_rate = f"{snapshot.get('churn_rate', 0) * 100:.1f}%"

    async def _decide_alert(self, mission_context: dict):
        """Phase 2: One small LLM call with Pydantic output."""
        # TODO: Call LLM with Pydantic AI structured output
        # Input: typed dict — numbers only
        # Output: { should_alert: bool, severity: str, primary_signal: str }

        self.state.alert_decision = {
            "should_alert": True,
            "severity": "warning",
            "primary_signal": self.state.triggered_patterns[0],
        }

    async def _generate_narrative(self):
        """Phase 3: Bounded narrative generation."""
        # TODO: Call LLM with max_tokens=120, max 200 words

        pattern = self.state.alert_decision["primary_signal"]
        self.state.narrative = f"BI Alert: {pattern} triggered. Check analytics dashboard for details."

    def get_alert(self) -> dict | None:
        """Get the alert to send to Slack."""
        if not self.state.alert_decision or not self.state.alert_decision.get("should_alert"):
            return None

        return {
            "agent": "BI Analyst",
            "severity": self.state.alert_decision.get("severity", "warning"),
            "pattern": self.state.alert_decision.get("primary_signal"),
            "narrative": self.state.narrative,
            "tenant_id": self.state.tenant_id,
            # Per PRD Section 11: Include domain fields
            "mrr_trend": self.state.mrr_trend,
            "churn_rate": self.state.churn_rate,
        }

    def get_domain_fields(self) -> dict:
        """Return domain fields to be written to MissionState."""
        return {
            "mrr_trend": self.state.mrr_trend,
            "churn_rate": self.state.churn_rate,
        }