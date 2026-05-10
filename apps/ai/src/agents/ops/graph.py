"""
Ops Watch Graph — LangGraph state machine.

Per PRD Section 8: Implements Generator → Reflector → Curator loop.
Phase 1: DATA ASSEMBLY (zero LLM) - pure Python
Phase 2: COGNITIVE DECISION (1 LLM) - Pydantic output
Phase 3: NARRATIVE GENERATION (1 LLM) - bounded 200 words

Per PRD Section 7: Agent persona - Ops Watch monitors:
- OG-01: Churn risk users (NPS < 5, no activity 7+ days)
- OG-02: Top feature ask (most requested in last 30 days)
- OG-03: Error spike (>3x baseline in 24h)
- OG-04: Support ticket escalation (priority tickets > 5)
- OG-05: Deployment failure (consecutive failed deploys)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Literal

log = logging.getLogger(__name__)


@dataclass
class OpsWatchState:
    """State for Ops Watch agent.

    Per PRD Section 8: Each employee agent maintains its own state.
    Co-founder agent orchestrates, employees execute.
    """

    tenant_id: str = ""
    triggered_patterns: list[str] = field(default_factory=list)
    ops_snapshot: dict | None = None
    alert_decision: dict | None = None
    narrative: str = ""
    confidence_score: float = 1.0

    # Per PRD Section 11: Domain fields written to MissionState
    churn_risk_users: list[str] = field(default_factory=list)  # user IDs
    top_feature_ask: str = ""  # e.g., "Dark mode", "API access"
    error_spike: bool = False  # True if error spike detected


class OpsWatchGraph:
    """LangGraph for Ops Watch.

    Implements Thin LLM, Fat Deterministic Core pattern:
    - Phase 1: Fetch all data (Python)
    - Phase 2: LLM decides if alert (Pydantic)
    - Phase 3: LLM generates narrative (bounded)
    """

    def __init__(self):
        self.state = OpsWatchState()

    async def run(self, tenant_id: str, mission_context: dict) -> OpsWatchState:
        """Run Ops Watch for a tenant.

        Args:
            tenant_id: The tenant to analyze
            mission_context: Current MissionState from shared context

        Returns:
            OpsWatchState with alert if triggered
        """
        log.info(f"Running Ops Watch for tenant: {tenant_id}")

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
        # TODO: Fetch from PostgreSQL, Sentry, Intercom, Linear
        # TODO: Compute churn risk, feature requests, error rates
        # TODO: Apply rule-based anomaly detection (if/elif)

        # Mock data - replace with real DB/API calls
        self.state.ops_snapshot = {
            "tenant_id": tenant_id,
            "churn_risk_users": [],
            "top_feature_ask": "",
            "error_count_24h": 0,
            "error_baseline": 0,
            "support_tickets_high_priority": 0,
            "failed_deploys": 0,
        }

        # Rule-based detection (zero LLM)
        patterns = []
        snapshot = self.state.ops_snapshot

        # OG-01: Churn risk users (NPS < 5, no activity 7+ days)
        churn_risk = snapshot.get("churn_risk_users", [])
        if len(churn_risk) > 0:
            patterns.append("OG-01")
            self.state.churn_risk_users = churn_risk

        # OG-02: Top feature ask
        top_feature = snapshot.get("top_feature_ask", "")
        if top_feature:
            patterns.append("OG-02")
            self.state.top_feature_ask = top_feature

        # OG-03: Error spike (>3x baseline in 24h)
        errors = snapshot.get("error_count_24h", 0)
        baseline = snapshot.get("error_baseline", 1)
        if errors > baseline * 3:
            patterns.append("OG-03")
            self.state.error_spike = True

        # OG-04: Support ticket escalation
        high_priority = snapshot.get("support_tickets_high_priority", 0)
        if high_priority > 5:
            patterns.append("OG-04")

        # OG-05: Deployment failure
        failed_deploys = snapshot.get("failed_deploys", 0)
        if failed_deploys >= 2:
            patterns.append("OG-05")

        self.state.triggered_patterns = patterns
        log.info(f"Ops Watch: {len(patterns)} patterns triggered")

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
        self.state.narrative = f"Ops Alert: {pattern} triggered. Check ops dashboard for details."

    def get_alert(self) -> dict | None:
        """Get the alert to send to Slack."""
        if not self.state.alert_decision or not self.state.alert_decision.get("should_alert"):
            return None

        return {
            "agent": "Ops Watch",
            "severity": self.state.alert_decision.get("severity", "warning"),
            "pattern": self.state.alert_decision.get("primary_signal"),
            "narrative": self.state.narrative,
            "tenant_id": self.state.tenant_id,
            # Per PRD Section 11: Include domain fields
            "churn_risk_users": self.state.churn_risk_users,
            "top_feature_ask": self.state.top_feature_ask,
            "error_spike": self.state.error_spike,
        }

    def get_domain_fields(self) -> dict:
        """Return domain fields to be written to MissionState."""
        return {
            "churn_risk_users": self.state.churn_risk_users,
            "top_feature_ask": self.state.top_feature_ask,
            "error_spike": self.state.error_spike,
        }

    def health_check(self) -> dict:
        """Return agent health status.

        Returns:
            dict with status, capability, owner, and latency_ms
        """
        start = time.perf_counter()
        try:
            # Quick deterministic check - no LLM needed
            _ = self.state.ops_snapshot
            latency_ms = int((time.perf_counter() - start) * 1000)
            return {
                "status": "ok",
                "capability": "ops.health_deployment",
                "owner": "ops-watch",
                "latency_ms": latency_ms,
            }
        except Exception as e:
            latency_ms = int((time.perf_counter() - start) * 1000)
            log.error(f"Ops Watch health check failed: {e}")
            return {
                "status": "error",
                "capability": "ops.health_deployment",
                "owner": "ops-watch",
                "latency_ms": latency_ms,
                "error": str(e),
            }