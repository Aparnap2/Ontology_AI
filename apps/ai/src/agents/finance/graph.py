"""
Finance Guardian Graph — LangGraph state machine.

Per PRD Section 8: Implements Generator → Reflector → Curator loop.
Phase 1: DATA ASSEMBLY (zero LLM) - pure Python
Phase 2: COGNITIVE DECISION (1 LLM) - Pydantic output
Phase 3: NARRATIVE GENERATION (1 LLM) - bounded 200 words
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

log = logging.getLogger(__name__)


@dataclass
class FinanceGuardianState:
    """State for Finance Guardian agent.

    Per PRD Section 8: Each employee agent maintains its own state.
    Co-founder agent orchestrates, employees execute.
    """

    tenant_id: str = ""
    triggered_patterns: list[str] = field(default_factory=list)
    financial_snapshot: dict | None = None
    alert_decision: dict | None = None
    narrative: str = ""
    confidence_score: float = 1.0


class FinanceGuardianGraph:
    """LangGraph for Finance Guardian.

    Implements Thin LLM, Fat Deterministic Core pattern:
    - Phase 1: Fetch all data (Python)
    - Phase 2: LLM decides if alert (Pydantic)
    - Phase 3: LLM generates narrative (bounded)
    """

    def __init__(self):
        self.state = FinanceGuardianState()

    async def run(self, tenant_id: str, mission_context: dict) -> FinanceGuardianState:
        """Run Finance Guardian for a tenant.

        Args:
            tenant_id: The tenant to analyze
            mission_context: Current MissionState from shared context

        Returns:
            FinanceGuardianState with alert if triggered
        """
        log.info(f"Running Finance Guardian for tenant: {tenant_id}")

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
        # TODO: Fetch from Stripe, PostgreSQL, Plaid
        # TODO: Compute burn, runway, MRR, churn
        # TODO: Apply rule-based anomaly detection (if/elif)

        self.state.financial_snapshot = {
            "tenant_id": tenant_id,
            "mrr": 0.0,
            "runway_days": 0,
            "burn_rate": 0.0,
            "churn_pct": 0.0,
        }

        # Rule-based detection (zero LLM)
        patterns = []
        snapshot = self.state.financial_snapshot

        if snapshot.get("churn_pct", 0) > 0.03:
            patterns.append("FG-01")

        if snapshot.get("runway_days", 999) < 180:
            patterns.append("FG-04")

        self.state.triggered_patterns = patterns
        log.info(f"Finance Guardian: {len(patterns)} patterns triggered")

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
        self.state.narrative = f"Finance alert: {pattern} triggered. See dashboard for details."

    def get_alert(self) -> dict | None:
        """Get the alert to send to Slack."""
        if not self.state.alert_decision or not self.state.alert_decision.get("should_alert"):
            return None

        return {
            "agent": "Finance Guardian",
            "severity": self.state.alert_decision.get("severity", "warning"),
            "pattern": self.state.alert_decision.get("primary_signal"),
            "narrative": self.state.narrative,
            "tenant_id": self.state.tenant_id,
        }