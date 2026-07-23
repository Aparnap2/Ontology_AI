"""Agent Authority Manifest — V5.1 canonical agent roster.

Defines each agent's domain, tool permissions, escalation tier, triggers,
and EngagementState fields it is allowed to write. Used by HITL routing,
tool execution guards, and EngagementState write-path validation.

V5.1: Six canonical agents replacing the legacy V4.1 roster.
- ChiefOfStaff (control_plane) — orchestrator / intent classifier
- Discovery (discovery) — evidence gathering
- OntologyMapper (ontology_mapping) — typed object materialization
- TruthAnalyst (truth_analysis) — blockers, contradictions, risks
- WorkflowBuilder (workflow_building) — governed draft generation
- Governance (governance) — approval routing, external action exclusivity
"""

from pydantic import BaseModel
from typing import Literal


class AgentAuthority(BaseModel):
    agent_name: str
    role: str
    voice: str
    domain: Literal[
        "control_plane",
        "discovery",
        "ontology_mapping",
        "truth_analysis",
        "workflow_building",
        "governance",
    ]
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
        agent_name="ChiefOfStaff",
        role="Orchestrator and intent classifier",
        voice="Strategic coordinator",
        domain="control_plane",
        can_emit_alerts=True,
        can_execute_tools=True,
        allowed_tool_ids=["classify_intent", "route_to_agent"],
        escalation_tier="review",
        triggers=["manual", "incoming_message"],
        writes_mission_fields=["phase", "operator_goal"],
        allowed_models=["gpt-4o"],
        external_facing=False,
        data_classification="internal",
    ),
    AgentAuthority(
        agent_name="Discovery",
        role="Evidence gathering and research",
        voice="Curious investigator",
        domain="discovery",
        can_emit_alerts=False,
        can_execute_tools=True,
        allowed_tool_ids=[
            "search_data_sources",
            "query_knowledge_base",
            "collect_evidence",
        ],
        escalation_tier="auto",
        triggers=["discovery_needed", "new_engagement"],
        writes_mission_fields=["discovery_notes", "data_sources", "freshness"],
        allowed_models=["gpt-4o-mini"],
        external_facing=False,
        data_classification="internal",
    ),
    AgentAuthority(
        agent_name="OntologyMapper",
        role="Ontology object and link materialization",
        voice="Knowledge architect",
        domain="ontology_mapping",
        can_emit_alerts=False,
        can_execute_tools=True,
        allowed_tool_ids=[
            "materialize_objects",
            "materialize_links",
            "validate_ontology",
        ],
        escalation_tier="auto",
        triggers=["discovery_complete"],
        writes_mission_fields=["ontology_objects", "ontology_links"],
        allowed_models=["gpt-4o-mini"],
        external_facing=False,
        data_classification="internal",
    ),
    AgentAuthority(
        agent_name="TruthAnalyst",
        role="Truth analysis, contradiction detection, and risk assessment",
        voice="Devil's advocate",
        domain="truth_analysis",
        can_emit_alerts=True,
        can_execute_tools=True,
        allowed_tool_ids=["flag_contradiction", "assess_risk", "flag_blocker"],
        escalation_tier="review",
        triggers=["ontology_complete", "risk_check_needed"],
        writes_mission_fields=[
            "truth_findings",
            "risk_analyses",
            "unresolved_questions",
        ],
        allowed_models=["gpt-4o-mini"],
        external_facing=False,
        data_classification="internal",
    ),
    AgentAuthority(
        agent_name="WorkflowBuilder",
        role="Governed workflow draft generation",
        voice="Solution architect",
        domain="workflow_building",
        can_emit_alerts=False,
        can_execute_tools=True,
        allowed_tool_ids=[
            "draft_workflow",
            "generate_solution_outline",
            "propose_change_strategy",
        ],
        escalation_tier="review",
        triggers=["truth_analysis_complete", "workflow_requested"],
        writes_mission_fields=[
            "workflow_specs",
            "executable_workflow_drafts",
            "change_strategies",
            "solution_evaluations",
        ],
        allowed_models=["gpt-4o-mini"],
        external_facing=False,
        data_classification="internal",
    ),
    AgentAuthority(
        agent_name="Governance",
        role="Approval routing and external action governance",
        voice="Compliance guardian",
        domain="governance",
        can_emit_alerts=True,
        can_execute_tools=True,
        allowed_tool_ids=[
            "route_for_approval",
            "approve_action",
            "reject_action",
            "escalate_to_human",
        ],
        escalation_tier="blocked",
        triggers=["approval_requested", "governance_check_needed"],
        writes_mission_fields=["planned_actions", "phase"],
        allowed_models=["gpt-4o"],
        external_facing=True,
        data_classification="restricted",
    ),
]

# O(1) lookup dict built from AUTHORITY_MANIFEST
AUTHORITY_MAP: dict[str, AgentAuthority] = {
    a.agent_name: a for a in AUTHORITY_MANIFEST
}
_AUTHORITY_BY_NAME: dict[str, AgentAuthority] = AUTHORITY_MAP


def get_authority(agent_name: str) -> AgentAuthority | None:
    """O(1) lookup of an agent's authority entry by canonical name."""
    return AUTHORITY_MAP.get(agent_name)


def can_execute_tool(agent_name: str, tool_id: str) -> bool:
    """Return True iff *agent_name* is allowed to execute *tool_id*."""
    auth = get_authority(agent_name)
    if auth is None:
        return False
    return tool_id in auth.allowed_tool_ids


def get_writes_mission_fields(agent_name: str) -> list[str]:
    """Return the EngagementState field names *agent_name* is allowed to patch."""
    auth = get_authority(agent_name)
    if auth is None:
        return []
    return auth.writes_mission_fields
