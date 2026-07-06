"""Self-Guardian Detector — deterministic deviation analysis for agent observations.

Evaluates agent observations against the authority manifest to detect
unauthorized tool usage, external-facing violations, and failure patterns.
No LLM calls — pure if/else logic.
"""
from __future__ import annotations

import logging
from datetime import datetime

from src.agents.authority_manifest import AUTHORITY_MANIFEST, get_authority
from src.schemas.self_guardian import (
    AgentObservation,
    DeviationType,
    SelfGuardianAlert,
    SelfGuardianReport,
)

log = logging.getLogger(__name__)

# Keywords in action or target_entity that suggest internal/restricted data access.
_INTERNAL_DATA_KEYWORDS = {
    "internal",
    "private",
    "confidential",
    "restricted",
    "secret",
    "pii",
    "credential",
    "password",
    "token",
    "ssn",
    "salary",
}


class SelfGuardianDetector:
    """Deterministic deviation detector for agent observations.

    Analyzes observations against the agent authority manifest and
    heuristic rules. Thread-safe by design — all state is read-only
    after construction.
    """

    def __init__(self) -> None:
        # Build a quick lookup: agent_name -> allowed_tool_ids set
        self._tool_map: dict[str, set[str]] = {}
        self._external_map: dict[str, bool] = {}
        for auth in AUTHORITY_MANIFEST:
            self._tool_map[auth.agent_name] = set(auth.allowed_tool_ids)
            self._external_map[auth.agent_name] = auth.external_facing

    def analyze(self, observation: AgentObservation) -> SelfGuardianAlert | None:
        """Analyze an observation and return an alert if a deviation is detected.

        Checks performed:
        1. Unauthorized tool usage — tool_id not in agent's allowed_tool_ids.
        2. External-facing violation — external_facing agent accessing internal data.
        3. Failure pattern — observation was not successful.

        Args:
            observation: The agent observation to analyze.

        Returns:
            A SelfGuardianAlert if a deviation is detected, None otherwise.
        """
        # Check 1: Unauthorized tool usage
        if observation.tool_id is not None:
            allowed = self._tool_map.get(observation.agent_name, set())
            if observation.tool_id not in allowed:
                log.warning(
                    "Unauthorized tool: agent=%s used tool=%s (allowed=%s)",
                    observation.agent_name,
                    observation.tool_id,
                    allowed,
                )
                return SelfGuardianAlert(
                    observation=observation,
                    deviation=DeviationType.UNAUTHORIZED_TOOL,
                    severity="critical",
                    description=(
                        f"Agent '{observation.agent_name}' used tool "
                        f"'{observation.tool_id}' which is not in its allowed "
                        f"tool list."
                    ),
                    suggested_action=(
                        f"Revoke access to '{observation.tool_id}' for "
                        f"'{observation.agent_name}' and investigate why it "
                        f"was invoked."
                    ),
                )

        # Check 2: External-facing violation
        is_external = self._external_map.get(observation.agent_name, False)
        if is_external:
            # Check if action or target_entity contains internal data keywords
            # Split on both whitespace and underscores to catch snake_case
            action_tokens = observation.action.lower().replace("_", " ").split()
            target_tokens = observation.target_entity.lower().replace("_", " ").split()
            if _INTERNAL_DATA_KEYWORDS & (set(action_tokens) | set(target_tokens)):
                log.warning(
                    "External-facing violation: agent=%s action=%s target=%s",
                    observation.agent_name,
                    observation.action,
                    observation.target_entity,
                )
                return SelfGuardianAlert(
                    observation=observation,
                    deviation=DeviationType.EXTERNAL_FACING_VIOLATION,
                    severity="warning",
                    description=(
                        f"External-facing agent '{observation.agent_name}' "
                        f"accessed data that may contain internal/restricted "
                        f"content (action='{observation.action}', "
                        f"target='{observation.target_entity}')."
                    ),
                    suggested_action=(
                        f"Review the action performed by "
                        f"'{observation.agent_name}' on "
                        f"'{observation.target_entity}' and ensure no "
                        f"internal data is exposed externally."
                    ),
                )

        # Check 3: Failed observation
        if not observation.success:
            log.info(
                "Failed observation: agent=%s action=%s error=%s",
                observation.agent_name,
                observation.action,
                observation.error_message,
            )
            return SelfGuardianAlert(
                observation=observation,
                deviation=DeviationType.STATE_CORRUPTION,
                severity="info",
                description=(
                    f"Agent '{observation.agent_name}' failed to execute "
                    f"action '{observation.action}'"
                    + (f": {observation.error_message}" if observation.error_message else ".")
                ),
                suggested_action=(
                    f"Investigate the failure for agent "
                    f"'{observation.agent_name}' on action "
                    f"'{observation.action}' and retry if appropriate."
                ),
            )

        return None

    def generate_report(
        self,
        observations: list[AgentObservation],
    ) -> SelfGuardianReport:
        """Generate an aggregated report from a list of observations.

        Args:
            observations: List of observations to summarize.

        Returns:
            A SelfGuardianReport with per-agent summaries and deviations.
        """
        if not observations:
            now = datetime.now()
            return SelfGuardianReport(
                window_start=now,
                window_end=now,
                total_observations=0,
                deviations=[],
                agent_summaries={},
            )

        timestamps = [o.timestamp for o in observations]
        window_start = min(timestamps)
        window_end = max(timestamps)

        # Collect per-agent data
        agent_observations: dict[str, list[AgentObservation]] = {}
        for obs in observations:
            agent_observations.setdefault(obs.agent_name, []).append(obs)

        # Run analysis on each observation
        deviations: list[SelfGuardianAlert] = []
        for obs in observations:
            alert = self.analyze(obs)
            if alert is not None:
                deviations.append(alert)

        # Build per-agent summaries
        agent_summaries: dict[str, dict] = {}
        for agent_name, agent_obs in agent_observations.items():
            total = len(agent_obs)
            agent_deviations = [d for d in deviations if d.observation.agent_name == agent_name]
            agent_durations = [o.duration_ms for o in agent_obs]
            avg_duration = sum(agent_durations) / len(agent_durations) if agent_durations else 0.0
            agent_summaries[agent_name] = {
                "total": total,
                "deviations": len(agent_deviations),
                "avg_duration_ms": round(avg_duration, 2),
            }

        return SelfGuardianReport(
            window_start=window_start,
            window_end=window_end,
            total_observations=len(observations),
            deviations=deviations,
            agent_summaries=agent_summaries,
        )
