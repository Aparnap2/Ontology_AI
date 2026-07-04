"""Control Plane schemas for agent registry, policy, risk, and audit."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from typing import Literal


class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskFlag(BaseModel):
    """A single risk flag detected during prompt or output scanning."""
    rule_id: str
    description: str
    severity: RiskSeverity
    matched_text: str


class RiskScanResult(BaseModel):
    """Result of a prompt or output risk scan.

    Attributes:
        status: "pass" (no flags), "flag" (issues found), "error"
        flags: List of RiskFlag objects
        severity: Overall severity ("low", "medium", "high")
        recommended_action: "proceed", "review", "block"
    """
    status: Literal["pass", "flag", "error"]
    flags: list[RiskFlag] = Field(default_factory=list)
    severity: RiskSeverity = RiskSeverity.LOW
    recommended_action: Literal["proceed", "review", "block"] = "proceed"


class PolicyDecision(BaseModel):
    """Outcome of a policy evaluation for an agent action.

    Attributes:
        data_classification: Classification of data involved ("internal", "external_investor", "external_customer", "restricted")
        allowed_model_classes: Which model classes are permitted (e.g. ["gpt-4o"], ["gpt-4o-mini"])
        requires_human_approval: Whether HITL approval is required
        blocked_reason: If blocked, the reason string; None if allowed
        approved_tools: List of tool names approved for this action
    """
    data_classification: str
    allowed_model_classes: list[str]
    requires_human_approval: bool
    blocked_reason: str | None = None
    approved_tools: list[str] = Field(default_factory=list)


class AuditEvent(BaseModel):
    """Audit log entry for a control-plane-gated agent action.

    Attributes:
        agent_name: Name of the agent that performed the action
        action: Type of action ("tool_execution", "mission_state_write", "alert_emit", "llm_invoke")
        tool_name: Name of the tool if action is tool_execution
        model_used: Model class used for LLM call
        policy_decision: The PolicyDecision that governed this action
        approval_state: "auto", "review", "approve", "blocked"
        outcome: "completed", "blocked", "failed"
        tenant_id: Tenant identifier
        timestamp: When the event occurred
        details: Optional additional context
    """
    agent_name: str
    action: Literal["tool_execution", "mission_state_write", "alert_emit", "llm_invoke"]
    tool_name: str | None = None
    model_used: str | None = None
    policy_decision: PolicyDecision | None = None
    approval_state: str | None = None
    outcome: Literal["completed", "blocked", "failed"]
    tenant_id: str
    timestamp: datetime | None = None
    details: dict | None = None


class AgentRegistration(BaseModel):
    """Registration record for an agent in the control plane.

    Attributes:
        agent_name: Unique agent name
        role: Human-readable role description
        domain: Domain literal ("finance", "bi", "ops", "cofounder", "correlation")
        allowed_tools: List of tool names this agent may execute
        allowed_models: List of model classes this agent may use
        escalation_tier: Default HITL tier ("auto", "review", "approve", "blocked")
        external_facing: Whether this agent produces external-facing outputs
        data_classification: Default data classification
        health_status: "healthy", "degraded", "unhealthy"
    """
    agent_name: str
    role: str
    domain: Literal["finance", "bi", "ops", "cofounder", "correlation"]
    allowed_tools: list[str]
    allowed_models: list[str]
    escalation_tier: Literal["auto", "review", "approve", "blocked"]
    external_facing: bool = False
    data_classification: str = "internal"
    health_status: Literal["healthy", "degraded", "unhealthy"] = "healthy"
