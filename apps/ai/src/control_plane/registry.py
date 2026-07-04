"""Agent Registry — typed registration and lookup.

All agents must register through this control plane before they
can emit alerts, propose tools, or write MissionState fields.
"""
from __future__ import annotations

import logging
import threading
from typing import Literal

from src.schemas.control_plane import AgentRegistration

log = logging.getLogger(__name__)


class ControlPlaneRegistry:
    """Thread-safe registry for agent registrations."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentRegistration] = {}
        self._lock = threading.Lock()

    def register(self, registration: AgentRegistration) -> None:
        """Register an agent. Replaces existing registration silently."""
        with self._lock:
            self._agents[registration.agent_name] = registration
            log.info(
                "Agent registered: %s (domain=%s, tier=%s, external=%s)",
                registration.agent_name,
                registration.domain,
                registration.escalation_tier,
                registration.external_facing,
            )

    def get(self, agent_name: str) -> AgentRegistration | None:
        """Look up an agent by name."""
        with self._lock:
            return self._agents.get(agent_name)

    def is_registered(self, agent_name: str) -> bool:
        """Check if an agent is registered."""
        with self._lock:
            return agent_name in self._agents

    def is_action_allowed(self, agent_name: str, tool_name: str) -> bool:
        """Check if the agent is allowed to execute a specific tool."""
        with self._lock:
            reg = self._agents.get(agent_name)
            if reg is None:
                return False
            return tool_name in reg.allowed_tools

    def list_agents(self) -> list[AgentRegistration]:
        """Return all registered agents."""
        with self._lock:
            return list(self._agents.values())

    def set_health(
        self, agent_name: str, status: Literal["healthy", "degraded", "unhealthy"]
    ) -> None:
        """Update an agent's health status."""
        with self._lock:
            reg = self._agents.get(agent_name)
            if reg is None:
                log.warning("Cannot set health for unknown agent: %s", agent_name)
                return
            self._agents[agent_name] = reg.model_copy(
                update={"health_status": status}
            )
            log.info(
                "Agent health updated: %s -> %s",
                agent_name,
                status,
            )