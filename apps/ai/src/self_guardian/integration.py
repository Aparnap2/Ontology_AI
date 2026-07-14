"""Integration layer — hooks Self-Guardian into agent lifecycle.

Wraps ObservationCollector, SelfGuardianDetector, and SelfGuardianPersister
into a single async context manager for seamless integration with agent workflows.

Usage:
    from src.self_guardian.integration import SelfGuardianIntegration

    async with SelfGuardianIntegration() as sgi:
        await sgi.record_agent_action("OntologyAI · Finance", "execute_tool", ...)
        report = await sgi.run_self_check()
"""
from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4

from src.schemas.self_guardian import (
    AgentObservation,
    SelfGuardianAlert,
    SelfGuardianReport,
)
from src.self_guardian.detector import SelfGuardianDetector
from src.self_guardian.monitor import ObservationCollector
from src.self_guardian.persister import SelfGuardianPersister

log = logging.getLogger(__name__)


class SelfGuardianIntegration:
    """Unified integration layer for the Self-Guardian subsystem.

    Combines observation collection, deviation detection, and alert
    persistence into a single interface that agent workflows can use
    as an async context manager.

    Args:
        persister: An optional ``SelfGuardianPersister`` instance. If
            omitted, a default one is created (which uses the default
            database URL).
    """

    def __init__(self, persister: SelfGuardianPersister | None = None) -> None:
        self.collector = ObservationCollector()
        self.detector = SelfGuardianDetector()
        self.persister = persister or SelfGuardianPersister()
        self._closed = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def record_agent_action(
        self,
        agent_name: str,
        action: str,
        tool_id: str | None = None,
        target_entity: str | None = None,
        success: bool = True,
        error_message: str | None = None,
        trace_id: str | None = None,
        duration_ms: int = 0,
    ) -> SelfGuardianAlert | None:
        """Record an agent action, detect deviations, and persist alerts.

        Creates an ``AgentObservation`` from the provided action metadata,
        records it in the in-memory buffer, runs the detector, and if a
        deviation is found, persists the alert to the database.

        Args:
            agent_name: Name of the agent that performed the action.
            action: Description of the action taken.
            tool_id: Identifier of the tool used, if any.
            target_entity: The entity the action was performed on.
            success: Whether the action completed successfully.
            error_message: Error details if the action failed.
            trace_id: Unique identifier for this trace/request. Auto-generated
                if not provided.
            duration_ms: How long the action took in milliseconds.

        Returns:
            A ``SelfGuardianAlert`` if a deviation was detected, ``None``
            if the observation was clean.
        """
        if self._closed:
            log.warning("SelfGuardianIntegration is closed; skipping record_agent_action")
            return None

        observation = AgentObservation(
            agent_name=agent_name,
            action=action,
            tool_id=tool_id,
            target_entity=target_entity or "",
            timestamp=datetime.now(),
            trace_id=trace_id or str(uuid4()),
            duration_ms=duration_ms,
            success=success,
            error_message=error_message,
        )

        # Record in the in-memory buffer
        self.collector.record_observation(observation)

        # Run deviation detection
        alert = self.detector.analyze(observation)

        # Persist alert if detected
        if alert is not None:
            await self.persister.store_alert(alert)

        # Always persist the observation to DB for dashboard visibility
        await self.persister.store_observation(observation)

        return alert

    async def record_alert(self, alert: SelfGuardianAlert) -> None:
        """Persist a single alert to the database.

        This is useful when an alert is generated outside the standard
        ``record_agent_action`` flow (e.g., from external detection).

        Args:
            alert: The ``SelfGuardianAlert`` to persist.
        """
        if self._closed:
            return
        await self.persister.store_alert(alert)

    async def run_self_check(
        self,
        tenant_id: str = "default",
    ) -> SelfGuardianReport:
        """Run a comprehensive self-check on all collected observations.

        Generates a report from all in-memory observations, persists any
        newly detected alerts to the database, and returns the report.

        Args:
            tenant_id: Tenant identifier for scoping alerts.

        Returns:
            A ``SelfGuardianReport`` with observations, deviations, and
            per-agent summaries.
        """
        observations = self.collector.get_observations()
        report = self.detector.generate_report(observations)

        # Persist any deviations that were found
        for alert in report.deviations:
            await self.persister.store_alert(alert)

        log.info(
            "Self-check complete: %d observations, %d deviations",
            report.total_observations,
            len(report.deviations),
        )
        return report

    async def close(self) -> None:
        """Release resources.

        Closes the persister's connection pool if it was internally created.
        Safe to call multiple times.
        """
        if self._closed:
            return
        self._closed = True
        await self.persister.close()
        log.info("SelfGuardianIntegration closed")

    # ------------------------------------------------------------------
    # Async context manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> SelfGuardianIntegration:
        """Enter async context manager, returning the integration instance."""
        self._closed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: object | None = None,
    ) -> None:
        """Exit async context manager, cleaning up resources."""
        await self.close()
