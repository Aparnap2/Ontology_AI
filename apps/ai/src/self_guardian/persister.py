"""Self-Guardian Persister — asyncpg-based PostgreSQL persistence for agent observations and alerts.

Follows the fail-soft pattern from audit.py and trust_battery_db.py:
- DB failures are logged, never raised to the caller.
- Connection pooling for efficient multi-write scenarios.
"""
from __future__ import annotations

import logging
from datetime import datetime

import asyncpg

from src.config.database import get_database_url
from src.schemas.self_guardian import AgentObservation, SelfGuardianAlert

log = logging.getLogger(__name__)

DATABASE_URL = get_database_url("iterateswarm")


class SelfGuardianPersister:
    """Persists Self-Guardian observations and alerts to PostgreSQL.

    Uses a connection pool for efficient multi-write scenarios.
    Fail-soft: all DB errors are logged and swallowed — never raised.

    Args:
        pool_or_url: An existing ``asyncpg.Pool``, a database URL string,
            or ``None`` to use the default ``DATABASE_URL``.
    """

    def __init__(self, pool_or_url: asyncpg.Pool | str | None = None) -> None:
        self._pool: asyncpg.Pool | None = None
        self._pool_or_url = pool_or_url

    async def _get_pool(self) -> asyncpg.Pool:
        """Return (or lazily create) the connection pool."""
        if self._pool is None:
            # If pool_or_url is a Pool, use it directly
            if isinstance(self._pool_or_url, asyncpg.Pool):
                self._pool = self._pool_or_url
            else:
                dsn = self._pool_or_url if isinstance(self._pool_or_url, str) else DATABASE_URL
                self._pool = await asyncpg.create_pool(
                    dsn,
                    min_size=1,
                    max_size=5,
                )
        return self._pool

    async def store_observation(self, observation: AgentObservation) -> None:
        """Persist a single agent observation.

        Fail-soft: logs error on DB failure, never raises.

        Args:
            observation: The AgentObservation to store.
        """
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO self_guardian_observations
                        (tenant_id, agent_name, action, tool_id, target_entity,
                         trace_id, duration_ms, success, error_message, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    "default",
                    observation.agent_name,
                    observation.action,
                    observation.tool_id,
                    observation.target_entity,
                    observation.trace_id,
                    observation.duration_ms,
                    observation.success,
                    observation.error_message,
                    observation.timestamp,
                )
            log.info(
                "Observation stored: agent=%s action=%s success=%s",
                observation.agent_name,
                observation.action,
                observation.success,
            )
        except Exception:
            log.exception(
                "Failed to store observation for agent=%s action=%s",
                observation.agent_name,
                observation.action,
            )

    async def store_alert(self, alert: SelfGuardianAlert) -> None:
        """Persist a single Self-Guardian alert.

        Fail-soft: logs error on DB failure, never raises.

        Args:
            alert: The SelfGuardianAlert to store.
        """
        obs = alert.observation
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO self_guardian_alerts
                        (tenant_id, agent_name, deviation_type, severity,
                         description, suggested_action,
                         observation_action, observation_tool_id, observation_success,
                         created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    "default",
                    obs.agent_name,
                    alert.deviation.value,
                    alert.severity,
                    alert.description,
                    alert.suggested_action,
                    obs.action,
                    obs.tool_id,
                    obs.success,
                    obs.timestamp,
                )
            log.info(
                "Alert stored: agent=%s deviation=%s severity=%s",
                obs.agent_name,
                alert.deviation.value,
                alert.severity,
            )
        except Exception:
            log.exception(
                "Failed to store alert for agent=%s deviation=%s",
                obs.agent_name,
                alert.deviation.value,
            )

    async def get_recent_alerts(
        self,
        tenant_id: str = "default",
        limit: int = 20,
    ) -> list[dict]:
        """Fetch the most recent alerts for a tenant.

        Fail-soft: returns empty list on DB failure.

        Args:
            tenant_id: Tenant to scope the query to.
            limit: Maximum number of alerts to return.

        Returns:
            A list of alert dicts ordered by ``created_at DESC``.
        """
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, tenant_id, agent_name, deviation_type, severity,
                           description, suggested_action,
                           observation_action, observation_tool_id, observation_success,
                           created_at
                    FROM self_guardian_alerts
                    WHERE tenant_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                    """,
                    tenant_id,
                    limit,
                )
            return [dict(row) for row in rows]
        except Exception:
            log.exception(
                "Failed to fetch recent alerts for tenant=%s",
                tenant_id,
            )
            return []

    async def get_agent_summary(
        self,
        tenant_id: str = "default",
        agent_name: str | None = None,
    ) -> list[dict]:
        """Return per-agent observation stats.

        Aggregates total observations, failure count, average duration,
        and last activity time. Optionally filtered to a single agent.

        Fail-soft: returns empty list on DB failure.

        Args:
            tenant_id: Tenant to scope the query to.
            agent_name: If set, only return stats for this agent.

        Returns:
            A list of dicts with keys: ``agent_name``, ``total``,
            ``failures``, ``avg_duration_ms``, ``last_active``.
        """
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                if agent_name is not None:
                    rows = await conn.fetch(
                        """
                        SELECT
                            agent_name,
                            COUNT(*)::int AS total,
                            COUNT(*) FILTER (WHERE NOT success)::int AS failures,
                            COALESCE(AVG(duration_ms)::int, 0) AS avg_duration_ms,
                            MAX(created_at) AS last_active
                        FROM self_guardian_observations
                        WHERE tenant_id = $1 AND agent_name = $2
                        GROUP BY agent_name
                        ORDER BY total DESC
                        """,
                        tenant_id,
                        agent_name,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT
                            agent_name,
                            COUNT(*)::int AS total,
                            COUNT(*) FILTER (WHERE NOT success)::int AS failures,
                            COALESCE(AVG(duration_ms)::int, 0) AS avg_duration_ms,
                            MAX(created_at) AS last_active
                        FROM self_guardian_observations
                        WHERE tenant_id = $1
                        GROUP BY agent_name
                        ORDER BY total DESC
                        """,
                        tenant_id,
                    )
            return [dict(row) for row in rows]
        except Exception:
            log.exception(
                "Failed to fetch agent summary for tenant=%s agent=%s",
                tenant_id,
                agent_name,
            )
            return []

    async def close(self) -> None:
        """Close the connection pool if it was created by this instance.

        Safe to call multiple times. Does **not** close a pool that was
        injected via the constructor (caller-managed lifecycle).

        A pool is considered "owned" (and thus closable) only when
        ``pool_or_url`` is ``None`` (use default DSN) or a URL string.
        In all other cases the pool is assumed to be externally managed.
        """
        if self._pool is not None:
            if self._pool_or_url is None or isinstance(self._pool_or_url, str):
                await self._pool.close()
            self._pool = None


# ---------------------------------------------------------------------------
# Convenience one-liner functions
# ---------------------------------------------------------------------------

async def store_observation(observation: AgentObservation) -> None:
    """One-liner: create persister, store observation, close.

    Args:
        observation: The AgentObservation to persist.
    """
    p = SelfGuardianPersister()
    try:
        await p.store_observation(observation)
    finally:
        await p.close()


async def store_alert(alert: SelfGuardianAlert) -> None:
    """One-liner: create persister, store alert, close.

    Args:
        alert: The SelfGuardianAlert to persist.
    """
    p = SelfGuardianPersister()
    try:
        await p.store_alert(alert)
    finally:
        await p.close()
