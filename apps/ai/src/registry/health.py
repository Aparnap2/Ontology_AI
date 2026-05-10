"""
Health Poller - Continuous capability health monitoring.

Per PRD: Router needs live health status to skip unhealthy capabilities.
HealthPoller runs background task to keep health status fresh.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Literal, Optional

from src.registry.registry import CapabilityRegistry

log = logging.getLogger(__name__)


class HealthPoller:
    """Polls capability health periodically and caches results.

    Attributes:
        registry: Capability registry to poll
        interval_seconds: Polling interval (default 30s)

    Usage:
        poller = HealthPoller(registry)
        await poller.start()
        health = poller.get_health("finance.runway_risk")
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        interval_seconds: int = 30,
    ):
        self.registry = registry
        self.interval = interval_seconds
        self._health_status: dict[str, Literal["ok", "degraded", "down"]] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start background health polling."""
        if self._running:
            log.warning("HealthPoller already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        log.info(f"HealthPoller started with {self.interval}s interval")

    async def stop(self) -> None:
        """Stop background health polling."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("HealthPoller stopped")

    async def _poll_loop(self) -> None:
        """Background polling loop."""
        # Initial poll
        await self._poll_all()

        while self._running:
            try:
                await asyncio.sleep(self.interval)
                await self._poll_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Health polling error: {e}")

    async def _poll_all(self) -> None:
        """Poll health of all registered capabilities."""
        for capability_id in self.registry._cache.keys():
            try:
                status = self.registry.health_check(capability_id)
                self._health_status[capability_id] = status
                if status != "ok":
                    log.warning(f"Capability {capability_id}: {status}")
            except Exception as e:
                log.error(f"Failed health check for {capability_id}: {e}")
                self._health_status[capability_id] = "down"

    def get_health(self, capability: str) -> Literal["ok", "degraded", "down"]:
        """Get last known health status for a capability.

        Args:
            capability: Capability ID (e.g., "finance.runway_risk")

        Returns:
            Health status: "ok", "degraded", or "down".
            Returns "unknown" if capability has never been polled.
        """
        return self._health_status.get(capability, "unknown")

    def is_healthy(self, capability: str) -> bool:
        """Check if a capability is healthy enough to use.

        Args:
            capability: Capability ID

        Returns:
            True if health is "ok" or "degraded" (usable with caution).
        """
        status = self.get_health(capability)
        return status in ("ok", "degraded")

    def get_unhealthy(self) -> list[str]:
        """Get list of capabilities that are down or degraded.

        Returns:
            List of unhealthy capability IDs.
        """
        return [
            cap for cap, status in self._health_status.items()
            if status in ("down", "degraded")
        ]