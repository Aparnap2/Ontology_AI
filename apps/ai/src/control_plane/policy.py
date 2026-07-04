"""Policy Engine — deterministic policy checks for agent actions.

Evaluates data classification, allowed models, external-facing status,
tool permissions, and health state. No LLM calls.
"""
from __future__ import annotations

import logging

from src.schemas.control_plane import AgentRegistration, PolicyDecision

log = logging.getLogger(__name__)

# Restricted data classifications that block all agent actions
_RESTRICTED_CLASSIFICATIONS = {"restricted", "pii", "confidential"}


class PolicyEngine:
    """Deterministic policy evaluation for agent actions."""

    def evaluate(
        self,
        agent: AgentRegistration,
        requested_tool: str | None = None,
    ) -> PolicyDecision:
        """Evaluate whether an agent action is permitted.

        Args:
            agent: The registered agent attempting the action.
            requested_tool: The specific tool being requested, if any.

        Returns:
            PolicyDecision with approval state and constraints.
        """
        approved_tools: list[str] = []
        requires_human_approval = False
        blocked_reason: str | None = None

        # 1. Health check — unhealthy agents are blocked
        if agent.health_status == "unhealthy":
            blocked_reason = "agent_health_unhealthy"
            log.warning(
                "Policy block: agent %s is unhealthy",
                agent.agent_name,
            )
            return PolicyDecision(
                data_classification=agent.data_classification,
                allowed_model_classes=[],
                requires_human_approval=True,
                blocked_reason=blocked_reason,
                approved_tools=[],
            )

        # 2. Data classification check — restricted data blocks
        if agent.data_classification.lower() in _RESTRICTED_CLASSIFICATIONS:
            blocked_reason = "data_classification_restricted"
            log.warning(
                "Policy block: agent %s has restricted classification: %s",
                agent.agent_name,
                agent.data_classification,
            )
            return PolicyDecision(
                data_classification=agent.data_classification,
                allowed_model_classes=[],
                requires_human_approval=True,
                blocked_reason=blocked_reason,
                approved_tools=[],
            )

        # 3. External-facing check — forces human approval
        if agent.external_facing:
            requires_human_approval = True

        # 4. Degraded health — forces review but not full block
        if agent.health_status == "degraded":
            requires_human_approval = True
            blocked_reason = "agent_health_degraded"

        # 5. Tool permission check
        if requested_tool is not None:
            if requested_tool in agent.allowed_tools:
                approved_tools.append(requested_tool)
            else:
                if blocked_reason is None:
                    blocked_reason = f"tool_not_allowed: {requested_tool}"
                requires_human_approval = True

        # 6. Determine allowed model classes
        allowed_models = agent.allowed_models
        if blocked_reason is not None:
            allowed_models = []

        return PolicyDecision(
            data_classification=agent.data_classification,
            allowed_model_classes=allowed_models,
            requires_human_approval=requires_human_approval,
            blocked_reason=blocked_reason,
            approved_tools=approved_tools,
        )