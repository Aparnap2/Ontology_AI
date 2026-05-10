"""Router: Co-founder message routing.

Routes messages to Employee Agents based on relevance gate and MissionState.
Per PRD Section 7: #sarthi channel as shared session.
Per PRD Section 220-224: Option C authority (low severity decides, critical escalates).
"""
from dataclasses import dataclass
from typing import Optional

from src.session.mission_state import get_mission_state, MissionState
from src.session.relevance_gate import evaluate_relevance, get_triggered_agents


@dataclass
class RouteDecision:
    """Result of routing decision."""

    destination: str  # "finance" | "bi" | "ops" | "none"
    reason: str
    should_escalate: bool
    triggered_agents: list[str] = None


class Router:
    """Co-founder router for message dispatch.

    Per PRD Section 7:
    - Agent responds only if: keyword_hit OR (active_alert AND question)
    - Never responds to every message — that is noise
    """

    def __init__(self):
        pass

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
        # Step 1: Get MissionState for context
        mission_state = await get_mission_state(tenant_id)

        # Step 2: Run relevance gate (pure Python, zero LLM)
        active_alerts = mission_state.active_alerts.split(",") if mission_state.active_alerts else []
        active_alerts = [a.strip() for a in active_alerts if a.strip()]

        relevance = evaluate_relevance(message, active_alerts)

        if not relevance.should_respond:
            return RouteDecision(
                destination="none",
                reason=relevance.reason,
                should_escalate=False,
                triggered_agents=[],
            )

        # Step 3: Get agent names from domains
        triggered_agents = get_triggered_agents(message, active_alerts)

        # Step 4: Check for escalation per PRD Option C
        should_escalate = self._should_escalate(message, mission_state)

        if should_escalate:
            return RouteDecision(
                destination="escalate",
                reason="Critical signal or investor update - requires founder approval",
                should_escalate=True,
                triggered_agents=triggered_agents,
            )

        # Step 5: Primary domain routing (deterministic)
        # Map domain → agent
        return RouteDecision(
            destination=relevance.triggered_domains[0] if relevance.triggered_domains else "none",
            reason=relevance.reason,
            should_escalate=False,
            triggered_agents=triggered_agents,
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