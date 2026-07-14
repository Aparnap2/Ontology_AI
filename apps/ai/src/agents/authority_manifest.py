"""Agent Authority Manifest — declarative capability/escalation registry.

Defines each agent's domain, tool permissions, escalation tier, triggers,
and MissionState fields it is allowed to write. Used by HITL routing,
tool execution guards, and MissionState write-path validation.

TrackGuard V4.1: All agent names use canonical display names.
"""
from pydantic import BaseModel
from typing import Literal


class AgentAuthority(BaseModel):
    agent_name: str
    role: str
    voice: str
    domain: Literal["finance", "bi", "ops", "cofounder", "correlation"]
    can_emit_alerts: bool
    can_execute_tools: bool
    allowed_tool_ids: list[str]
    escalation_tier: Literal["auto", "review", "approve", "blocked"]
    triggers: list[str]
    writes_mission_fields: list[str]
    allowed_models: list[str] = ["gpt-4o-mini"]
    external_facing: bool = False
    data_classification: str = "internal"


AUTHORITY_MANIFEST: list[AgentAuthority] = [
    AgentAuthority(
        agent_name="Chief of Staff",
        role="manager/cofounder",
        voice="Founder's strategic thinking partner",
        domain="cofounder",
        can_emit_alerts=True,
        can_execute_tools=True,
        allowed_tool_ids=["draft_investor_update"],
        escalation_tier="approve",
        triggers=["manual", "schedule"],
        writes_mission_fields=["founder_focus", "active_alerts", "prepared_brief"],
        allowed_models=["gpt-4o"],
        external_facing=True,
        data_classification="external_investor",
    ),
    AgentAuthority(
        agent_name="FP&A",
        role="Finance specialist",
        voice="Financial guardian",
        domain="finance",
        can_emit_alerts=True,
        can_execute_tools=True,
        allowed_tool_ids=["pause_failed_payment_retry"],
        escalation_tier="review",
        triggers=["FG-01", "FG-02", "FG-03", "FG-04", "FG-05", "FG-06"],
        writes_mission_fields=["runway_days", "burn_alert", "burn_severity", "burn_multiple"],
        allowed_models=["gpt-4o-mini"],
        external_facing=False,
        data_classification="internal",
    ),
    AgentAuthority(
        agent_name="Growth Analytics",
        role="BI specialist",
        voice="Data analyst",
        domain="bi",
        can_emit_alerts=True,
        can_execute_tools=True,
        allowed_tool_ids=["draft_investor_update"],
        escalation_tier="auto",
        triggers=["BG-01", "BG-02", "BG-03", "BG-04", "BG-05", "BG-06"],
        writes_mission_fields=["mrr_trend", "churn_rate"],
        allowed_models=["gpt-4o-mini"],
        external_facing=False,
        data_classification="internal",
    ),
    AgentAuthority(
        agent_name="Reliability & Delivery",
        role="Ops specialist",
        voice="Operations watchdog",
        domain="ops",
        can_emit_alerts=True,
        can_execute_tools=True,
        allowed_tool_ids=["flag_churn_risk_customer", "schedule_customer_checkin"],
        escalation_tier="auto",
        triggers=["OG-01", "OG-02", "OG-03", "OG-04", "OG-05"],
        writes_mission_fields=["churn_risk_users", "top_feature_ask", "error_spike"],
        allowed_models=["gpt-4o-mini"],
        external_facing=False,
        data_classification="internal",
    ),
    AgentAuthority(
        agent_name="Communications",
        role="Communications specialist",
        voice="Stakeholder communications manager",
        domain="ops",
        can_emit_alerts=False,
        can_execute_tools=True,
        allowed_tool_ids=["draft_investor_update"],
        escalation_tier="auto",
        triggers=["manual"],
        writes_mission_fields=[],
        allowed_models=["gpt-4o-mini"],
        external_facing=True,
        data_classification="external_investor",
    ),
    AgentAuthority(
        agent_name="Correlation Agent",
        role="Cross-domain synthesizer",
        voice="Pattern detector",
        domain="correlation",
        can_emit_alerts=True,
        can_execute_tools=False,
        allowed_tool_ids=[],
        escalation_tier="review",
        triggers=["cross-domain"],
        writes_mission_fields=["active_alerts"],
        allowed_models=["gpt-4o-mini"],
        external_facing=False,
        data_classification="internal",
    ),
]


def get_authority(agent_name: str) -> AgentAuthority | None:
    for a in AUTHORITY_MANIFEST:
        if a.agent_name == agent_name:
            return a
    return None


def can_execute_tool(agent_name: str, tool_id: str) -> bool:
    auth = get_authority(agent_name)
    if auth is None:
        return False
    return tool_id in auth.allowed_tool_ids


def get_writes_mission_fields(agent_name: str) -> list[str]:
    auth = get_authority(agent_name)
    if auth is None:
        return []
    return auth.writes_mission_fields
