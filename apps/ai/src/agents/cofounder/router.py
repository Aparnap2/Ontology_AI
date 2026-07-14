"""Router: Co-founder message routing.

Routes messages to Employee Agents based on relevance gate and MissionState.
Per PRD Section 7: #ontology_ai channel as shared session.
Per PRD Section 220-224: Option C authority (low severity decides, critical escalates).
"""
from dataclasses import dataclass
from typing import Optional

from src.registry.health import HealthPoller
from src.session.mission_state import get_mission_state, MissionState
from src.session.relevance_gate import evaluate_relevance, get_triggered_agents
from src.services.trust_battery import (
    AgentTrustProfile,
    DEGRADED_THRESHOLD,
    get_profile,
    is_agent_degraded,
    update_trust_score,
)

DEGRADED_PRIORITY = 999
MEDIUM_TRUST_THRESHOLD = 0.6

# Capability to domain mapping
CAPABILITY_DOMAIN_MAP = {
    "finance.runway_risk": "finance",
    "bi.cohort_retention": "bi",
    "ops.error_correlation": "ops",
    "memory.similar_alerts": "memory",
    "graphiti.strategy_lookup": "graphiti",
    "service.api-gateway": "service",
    "service.workflow": "service",
}


@dataclass
class RouteDecision:
    """Result of routing decision."""

    destination: str  # "finance" | "bi" | "ops" | "none"
    reason: str
    should_escalate: bool
    triggered_agents: list[str] = None
    trust_score: float = 0.0
    routing_priority: int = 999
    trust_reason: str = ""


class Router:
    """Co-founder router for message dispatch.

    Per PRD Section 7:
    - Agent responds only if: keyword_hit OR (active_alert AND question)
    - Never responds to every message — that is noise

    Per PRD: Includes HealthPoller to skip unhealthy capabilities.
    """

    def __init__(
        self,
        registry=None,
        health_poller: Optional[HealthPoller] = None,
    ):
        """Initialize router with optional registry and health poller.

        Args:
            registry: Capability registry (loads default if None)
            health_poller: Health poller for capability health checks
        """
        from src.registry.registry import CapabilityRegistry
        self.registry = registry or CapabilityRegistry()
        self.health_poller = health_poller

    def _check_capability_health(self, domain: str) -> tuple[bool, str]:
        """Check if capability for domain is healthy.

        Args:
            domain: Target domain (finance, bi, ops)

        Returns:
            Tuple of (is_healthy, reason)
        """
        if self.health_poller is None:
            return True, "no health poller configured"

        for cap_id, cap_domain in CAPABILITY_DOMAIN_MAP.items():
            if cap_domain == domain:
                health = self.health_poller.get_health(cap_id)
                if health == "down":
                    return False, f"{cap_id} is down"
                elif health == "degraded":
                    return True, f"{cap_id} is degraded"
                return True, f"{cap_id} is {health}"
        return True, "no capability mapping found"

    def _get_trust_info(self, tenant_id: str, agent_name: str) -> tuple[float, str, str]:
        """Get trust score and reason for agent.

        Returns:
            Tuple of (trust_score, reason, trust_level)
        """
        profile = get_profile(tenant_id, agent_name)
        score = profile.trust_score
        priority = profile.route_priority

        if score < DEGRADED_THRESHOLD:
            return score, f"Agent {agent_name} is degraded (trust={score:.2f}, priority={priority})", "degraded"
        if score < MEDIUM_TRUST_THRESHOLD:
            return score, f"Agent {agent_name} has medium trust (trust={score:.2f})", "medium"
        return score, f"Agent {agent_name} has high trust (trust={score:.2f})", "high"

    def _route_degraded(self, domain: str, trust_score: float, reason: str) -> RouteDecision:
        """Route in degraded mode - use simpler checks, reduce complexity."""
        return RouteDecision(
            destination=domain,
            reason=f"Degraded mode: {reason}",
            should_escalate=False,
            triggered_agents=[],
            trust_score=trust_score,
            routing_priority=DEGRADED_PRIORITY,
            trust_reason="degraded_mode_active",
        )

    def _route_with_caveat(self, domain: str, trust_score: float, reason: str) -> RouteDecision:
        """Route with caution - medium trust requires extra validation."""
        return RouteDecision(
            destination=domain,
            reason=f"Caution: {reason}",
            should_escalate=False,
            triggered_agents=[],
            trust_score=trust_score,
            routing_priority=3,
            trust_reason="medium_trust_caveat",
        )

    def _route_full(
        self,
        domain: str,
        base_reason: str,
        triggered_agents: list[str],
        trust_score: float,
        priority: int,
    ) -> RouteDecision:
        """Full pipeline routing - high trust agent."""
        return RouteDecision(
            destination=domain,
            reason=base_reason,
            should_escalate=False,
            triggered_agents=triggered_agents,
            trust_score=trust_score,
            routing_priority=priority,
            trust_reason="full_trust_pipeline",
        )

    def _fallback_route(self, domain: str) -> RouteDecision:
        """Route to fallback when capability is unhealthy."""
        return RouteDecision(
            destination="none",
            reason=f"Capability for {domain} is unhealthy - using fallback",
            should_escalate=False,
            triggered_agents=[],
            trust_score=0.0,
            routing_priority=DEGRADED_PRIORITY,
            trust_reason="capability_unhealthy",
        )

    async def route(
        self,
        message: str,
        tenant_id: str,
    ) -> RouteDecision:
        """Route message to appropriate employee agent.

        Args:
            message: User message text
            tenant_id: The tenant for context

        Returns:
            RouteDecision with destination and reason
        """
        mission_state = await get_mission_state(tenant_id)

        active_alerts = mission_state.active_alerts.split(",") if mission_state.active_alerts else []
        active_alerts = [a.strip() for a in active_alerts if a.strip()]

        relevance = evaluate_relevance(message, active_alerts)

        if not relevance.should_respond:
            return RouteDecision(
                destination="none",
                reason=relevance.reason,
                should_escalate=False,
                triggered_agents=[],
                trust_score=0.75,
                routing_priority=1,
                trust_reason="no_relevance",
            )

        triggered_agents = get_triggered_agents(message, active_alerts)

        should_escalate = self._should_escalate(message, mission_state)

        if should_escalate:
            return RouteDecision(
                destination="escalate",
                reason="Critical signal or investor update - requires founder approval",
                should_escalate=True,
                triggered_agents=triggered_agents,
                trust_score=0.75,
                routing_priority=1,
                trust_reason="critical_escalation",
            )

        target_domain = relevance.triggered_domains[0] if relevance.triggered_domains else "none"

        if target_domain != "none":
            is_healthy, health_reason = self._check_capability_health(target_domain)
            if not is_healthy:
                return self._fallback_route(target_domain)

            agent_name = triggered_agents[0] if triggered_agents else target_domain
            trust_score, trust_reason_str, trust_level = self._get_trust_info(tenant_id, agent_name)

            if trust_level == "degraded":
                return self._route_degraded(target_domain, trust_score, trust_reason_str)

            if trust_level == "medium":
                return self._route_with_caveat(target_domain, trust_score, trust_reason_str)

            profile = get_profile(tenant_id, agent_name)
            return self._route_full(
                target_domain,
                relevance.reason,
                triggered_agents,
                trust_score,
                profile.route_priority,
            )

        return RouteDecision(
            destination=target_domain,
            reason=relevance.reason,
            should_escalate=False,
            triggered_agents=triggered_agents,
            trust_score=0.75,
            routing_priority=1,
            trust_reason="default_routing",
        )

    def _should_escalate(
        self,
        message: str,
        mission_state: Optional[MissionState],
    ) -> bool:
        """Determine if message requires escalation.

        Per PRD Option C:
        - Critical signals
        - Confidence < 0.60
        - Investor update drafts (always requires approval)
        """
        if mission_state is None:
            return False

        # Check for critical signals
        if mission_state.burn_alert:
            if mission_state.burn_severity in ["critical", "high"]:
                return True

        # Check for investor-related keywords (always escalates per PRD)
        investor_keywords = ["investor", "update", "brief", "quarterly", "fundraising", "raise"]
        message_lower = message.lower()
        for kw in investor_keywords:
            if kw in message_lower:
                return True

        return False


async def route_message(
    message: str,
    tenant_id: str,
) -> RouteDecision:
    """Convenience function for routing."""
    router = Router()
    return await router.route(message, tenant_id)


# Agent execution functions (to be wired)
async def run_finance_guardian(tenant_id: str, message: str) -> dict:
    """Execute Finance Guardian agent.

    Per PRD Section 8: Thin LLM, Fat Deterministic Core.
    Phase 1: DATA ASSEMBLY (zero LLM)
    Phase 2: COGNITIVE DECISION (1 LLM)
    Phase 3: NARRATIVE GENERATION (1 LLM)
    """
    from src.agents.finance.graph import FinanceGuardianGraph

    mission_state = await get_mission_state(tenant_id)
    graph = FinanceGuardianGraph()
    state = await graph.run(tenant_id, mission_state.__dict__)

    return {
        "agent": "Finance Guardian",
        "alert": graph.get_alert(),
        "triggered_patterns": state.triggered_patterns,
    }


async def run_bi_analyst(tenant_id: str, message: str) -> dict:
    """Execute BI Analyst agent.

    Per PRD Section 8: Thin LLM, Fat Deterministic Core.
    Phase 1: DATA ASSEMBLY (zero LLM)
    Phase 2: COGNITIVE DECISION (1 LLM)
    Phase 3: NARRATIVE GENERATION (1 LLM)
    """
    from src.agents.bi.graph import BIAnalystGraph

    mission_state = await get_mission_state(tenant_id)
    graph = BIAnalystGraph()
    state = await graph.run(tenant_id, mission_state.__dict__)

    return {
        "agent": "BI Analyst",
        "alert": graph.get_alert(),
        "triggered_patterns": state.triggered_patterns,
        "domain_fields": graph.get_domain_fields(),
    }


async def run_ops_watch(tenant_id: str, message: str) -> dict:
    """Execute Ops Watch agent.

    Per PRD Section 8: Thin LLM, Fat Deterministic Core.
    Phase 1: DATA ASSEMBLY (zero LLM)
    Phase 2: COGNITIVE DECISION (1 LLM)
    Phase 3: NARRATIVE GENERATION (1 LLM)
    """
    from src.agents.ops.graph import OpsWatchGraph

    mission_state = await get_mission_state(tenant_id)
    graph = OpsWatchGraph()
    state = await graph.run(tenant_id, mission_state.__dict__)

    return {
        "agent": "Ops Watch",
        "alert": graph.get_alert(),
        "triggered_patterns": state.triggered_patterns,
        "domain_fields": graph.get_domain_fields(),
    }


# Agent execution map
AGENT_RUNNERS = {
    "Finance Guardian": run_finance_guardian,
    "BI Analyst": run_bi_analyst,
    "Ops Watch": run_ops_watch,
}