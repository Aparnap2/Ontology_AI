"""Observation Collector — thread-safe in-memory buffer for agent observations.

Stores AgentObservation records with a capped buffer, filtering
capabilities, and thread-safe access via threading.Lock().
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime

from src.schemas.self_guardian import AgentObservation

log = logging.getLogger(__name__)

_MAX_BUFFER_SIZE = 10000


class ObservationCollector:
    """Thread-safe buffer for collecting agent observations.

    Records observations in-memory with a fixed capacity. Older entries
    are discarded when the buffer exceeds capacity.
    """

    def __init__(self) -> None:
        self._observations: list[AgentObservation] = []
        self._lock = threading.Lock()

    def record_observation(self, observation: AgentObservation) -> None:
        """Record a single agent observation.

        If the buffer is at capacity, the oldest entry is removed.
        """
        with self._lock:
            if len(self._observations) >= _MAX_BUFFER_SIZE:
                self._observations.pop(0)
            self._observations.append(observation)
            log.debug(
                "Observation recorded for agent=%s action=%s success=%s",
                observation.agent_name,
                observation.action,
                observation.success,
            )

    def get_observations(
        self,
        agent_name: str | None = None,
        since: datetime | None = None,
    ) -> list[AgentObservation]:
        """Return observations, optionally filtered by agent and/or time.

        Args:
            agent_name: If set, only return observations for this agent.
            since: If set, only return observations after this timestamp.

        Returns:
            A list of matching AgentObservation records.
        """
        with self._lock:
            results = self._observations

            if agent_name is not None:
                results = [o for o in results if o.agent_name == agent_name]

            if since is not None:
                results = [o for o in results if o.timestamp >= since]

            return list(results)

    def clear(self) -> None:
        """Reset the observation buffer."""
        with self._lock:
            self._observations.clear()
            log.info("Observation buffer cleared")

    @property
    def count(self) -> int:
        """Return the current number of observations in the buffer."""
        with self._lock:
            return len(self._observations)
