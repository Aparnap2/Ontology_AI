"""Self-Guardian Persister tests — asyncpg mocked, no real DB connection.

Tests verify:
1. store_observation calls the correct SQL with expected parameters
2. store_alert calls the correct SQL with expected parameters
3. Fail-soft on DB error (logs instead of crashes)
4. Convenience one-liner functions work end-to-end
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.schemas.self_guardian import (
    AgentObservation,
    DeviationType,
    SelfGuardianAlert,
)
from src.self_guardian.persister import (
    SelfGuardianPersister,
    store_observation,
    store_alert,
)


# ---------------------------------------------------------------------------
# Fixtures — sample observations and alerts
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_observation() -> AgentObservation:
    return AgentObservation(
        agent_name="FP&A",
        action="execute_tool",
        tool_id="pause_failed_payment_retry",
        target_entity="payment:sub_abc123",
        timestamp=datetime(2025, 6, 1, 12, 0, 0),
        trace_id="trace-persist-001",
        duration_ms=150,
        success=True,
    )


@pytest.fixture
def sample_alert(sample_observation: AgentObservation) -> SelfGuardianAlert:
    return SelfGuardianAlert(
        observation=sample_observation,
        deviation=DeviationType.UNAUTHORIZED_TOOL,
        severity="critical",
        description="Agent 'FP&A' used tool 'unknown_tool'.",
        suggested_action="Revoke and investigate.",
    )


@pytest.fixture
def mock_pool():
    """Return a mock asyncpg.Pool with async context manager protocol.

    Uses MagicMock as the base and explicitly sets AsyncMock for
    ``close``, ``acquire``, and the connection's ``execute`` / ``fetch``
    methods to avoid Python 3.13 ``AsyncMock(spec=...)`` quirks.
    """
    # Mock connection returned by acquire()
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock()
    conn.fetchrow = AsyncMock()
    conn.close = AsyncMock()

    # Context manager returned by pool.acquire()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)

    # Pool itself
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    pool.close = AsyncMock()
    return pool


@pytest.fixture
def patched_persister(mock_pool):
    """Return a SelfGuardianPersister whose pool is pre-configured to ``mock_pool``."""
    persister = SelfGuardianPersister(pool_or_url=mock_pool)
    persister._pool = mock_pool
    return persister


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_conn(mock_pool):
    """Return the mock connection from the pool's acquire context manager."""
    return mock_pool.acquire.return_value.__aenter__.return_value


def _get_sql_and_params(execute_mock: AsyncMock):
    """Extract SQL string and params tuple from an execute/fetch call."""
    args = execute_mock.call_args[0]
    return args[0], args[1:]


# ---------------------------------------------------------------------------
# SelfGuardianPersister Tests
# ---------------------------------------------------------------------------

class TestStoreObservation:
    """Tests for ``SelfGuardianPersister.store_observation``."""

    async def test_calls_execute_with_correct_sql(
        self,
        patched_persister: SelfGuardianPersister,
        mock_pool,
        sample_observation: AgentObservation,
    ):
        """Verify the correct SQL template and parameters are sent to the DB."""
        await patched_persister.store_observation(sample_observation)

        conn = _get_conn(mock_pool)
        conn.execute.assert_called_once()
        sql, params = _get_sql_and_params(conn.execute)

        # Check SQL contains the right table and columns
        assert "INSERT INTO self_guardian_observations" in sql
        assert "$1" in sql

        # Check parameters match the observation
        assert params[0] == "default"  # tenant_id
        assert params[1] == sample_observation.agent_name
        assert params[2] == sample_observation.action
        assert params[3] == sample_observation.tool_id
        assert params[4] == sample_observation.target_entity
        assert params[5] == sample_observation.trace_id
        assert params[6] == sample_observation.duration_ms
        assert params[7] == sample_observation.success
        assert params[8] == sample_observation.error_message
        assert params[9] == sample_observation.timestamp

    async def test_logs_and_swallows_db_error(
        self,
        patched_persister: SelfGuardianPersister,
        mock_pool,
        sample_observation: AgentObservation,
    ):
        """DB errors during execute should be logged but not raised."""
        conn = _get_conn(mock_pool)
        conn.execute.side_effect = Exception("Connection refused")

        # Should not raise
        await patched_persister.store_observation(sample_observation)

    async def test_store_observation_success_path(
        self,
        patched_persister: SelfGuardianPersister,
        sample_observation: AgentObservation,
    ):
        """Happy path: no exception should be raised."""
        await patched_persister.store_observation(sample_observation)


class TestStoreAlert:
    """Tests for ``SelfGuardianPersister.store_alert``."""

    async def test_calls_execute_with_correct_sql(
        self,
        patched_persister: SelfGuardianPersister,
        mock_pool,
        sample_alert: SelfGuardianAlert,
    ):
        """Verify the correct SQL template and parameters for alert storage."""
        await patched_persister.store_alert(sample_alert)

        conn = _get_conn(mock_pool)
        conn.execute.assert_called_once()
        sql, params = _get_sql_and_params(conn.execute)

        # Check SQL contains the right table
        assert "INSERT INTO self_guardian_alerts" in sql
        assert "$1" in sql

        # Check parameters
        assert params[0] == "default"  # tenant_id
        assert params[1] == sample_alert.observation.agent_name
        assert params[2] == sample_alert.deviation.value
        assert params[3] == sample_alert.severity
        assert params[4] == sample_alert.description
        assert params[5] == sample_alert.suggested_action
        assert params[6] == sample_alert.observation.action
        assert params[7] == sample_alert.observation.tool_id
        assert params[8] == sample_alert.observation.success

    async def test_logs_and_swallows_db_error(
        self,
        patched_persister: SelfGuardianPersister,
        mock_pool,
        sample_alert: SelfGuardianAlert,
    ):
        """DB errors on alert store should be logged but not raised."""
        conn = _get_conn(mock_pool)
        conn.execute.side_effect = Exception("DB unavailable")

        # Should not raise
        await patched_persister.store_alert(sample_alert)


class TestGetRecentAlerts:
    """Tests for ``SelfGuardianPersister.get_recent_alerts``."""

    async def test_returns_list_of_dicts(
        self,
        patched_persister: SelfGuardianPersister,
        mock_pool,
    ):
        """Should return a list of dicts with expected keys."""
        conn = _get_conn(mock_pool)
        conn.fetch.return_value = [
            {
                "id": "uuid-1",
                "tenant_id": "default",
                "agent_name": "FP&A",
                "deviation_type": "unauthorized_tool",
                "severity": "critical",
                "description": "Test",
                "suggested_action": "Investigate",
                "observation_action": "execute_tool",
                "observation_tool_id": "bad_tool",
                "observation_success": False,
                "created_at": datetime(2025, 6, 1, 12, 0, 0),
            }
        ]

        result = await patched_persister.get_recent_alerts(tenant_id="default", limit=10)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["agent_name"] == "FP&A"
        assert result[0]["deviation_type"] == "unauthorized_tool"

    async def test_returns_empty_list_on_db_error(
        self,
        patched_persister: SelfGuardianPersister,
    ):
        """DB errors should yield empty list, not crash."""
        with patch.object(patched_persister, "_get_pool") as mock_get_pool:
            mock_get_pool.side_effect = Exception("DB gone")
            result = await patched_persister.get_recent_alerts()
            assert result == []


class TestGetAgentSummary:
    """Tests for ``SelfGuardianPersister.get_agent_summary``."""

    async def test_returns_aggregated_stats(
        self,
        patched_persister: SelfGuardianPersister,
        mock_pool,
    ):
        """Should return per-agent aggregated stats as list of dicts."""
        conn = _get_conn(mock_pool)
        conn.fetch.return_value = [
            {
                "agent_name": "FP&A",
                "total": 10,
                "failures": 2,
                "avg_duration_ms": 150,
                "last_active": datetime(2025, 6, 1, 12, 0, 0),
            }
        ]

        result = await patched_persister.get_agent_summary(tenant_id="default")
        assert len(result) == 1
        assert result[0]["agent_name"] == "FP&A"
        assert result[0]["total"] == 10
        assert result[0]["failures"] == 2

    async def test_filters_by_agent_name(
        self,
        patched_persister: SelfGuardianPersister,
        mock_pool,
    ):
        """When agent_name is provided, only that agent's stats are fetched."""
        conn = _get_conn(mock_pool)

        await patched_persister.get_agent_summary(
            tenant_id="default",
            agent_name="FP&A",
        )

        conn.fetch.assert_called_once()
        sql = conn.fetch.call_args[0][0]
        # Should include a WHERE clause filtering by agent_name
        assert "agent_name" in sql

    async def test_returns_empty_list_on_db_error(
        self,
        patched_persister: SelfGuardianPersister,
    ):
        """DB errors should yield empty list."""
        with patch.object(patched_persister, "_get_pool") as mock_get_pool:
            mock_get_pool.side_effect = Exception("DB gone")
            result = await patched_persister.get_agent_summary()
            assert result == []


class TestClose:
    """Tests for ``SelfGuardianPersister.close``."""

    async def test_close_own_pool(self):
        """close() should close the pool when created internally."""
        mock_pool = MagicMock()
        mock_pool.close = AsyncMock()
        persister = SelfGuardianPersister(pool_or_url="postgresql://localhost/test")
        persister._pool = mock_pool
        await persister.close()
        mock_pool.close.assert_awaited_once()
        assert persister._pool is None

    async def test_close_external_pool_not_closed(self, mock_pool):
        """close() should NOT close an externally-provided pool."""
        persister = SelfGuardianPersister(pool_or_url=mock_pool)
        persister._pool = mock_pool
        await persister.close()
        mock_pool.close.assert_not_called()


class TestPoolLazyInit:
    """Tests that the pool is lazily created on first write."""

    async def test_pool_not_created_at_init(self):
        """Pool should be None until first use."""
        persister = SelfGuardianPersister()
        assert persister._pool is None

    async def test_pool_created_on_first_store(self):
        """Pool should be created when store_observation is called."""
        with patch(
            "src.self_guardian.persister.asyncpg.create_pool",
            new_callable=AsyncMock,
        ) as mock_create:
            conn = MagicMock()
            conn.execute = AsyncMock()
            conn.close = AsyncMock()

            acquire_cm = MagicMock()
            acquire_cm.__aenter__ = AsyncMock(return_value=conn)
            acquire_cm.__aexit__ = AsyncMock(return_value=None)

            mock_pool = MagicMock()
            mock_pool.acquire = MagicMock(return_value=acquire_cm)
            mock_pool.close = AsyncMock()
            mock_create.return_value = mock_pool

            obs = AgentObservation(
                agent_name="Test",
                action="test",
                target_entity="test",
                timestamp=datetime.now(),
                trace_id="trace-test",
                duration_ms=100,
                success=True,
            )
            persister = SelfGuardianPersister()
            await persister.store_observation(obs)
            mock_create.assert_awaited_once()
            assert persister._pool is not None
            await persister.close()


# ---------------------------------------------------------------------------
# Convenience one-liner function tests
# ---------------------------------------------------------------------------

class TestConvenienceFunctions:
    """Tests for module-level ``store_observation()`` and ``store_alert()``."""

    async def test_store_observation_convenience(
        self,
        sample_observation: AgentObservation,
    ):
        """The one-liner should create persister, store, and close."""
        with patch(
            "src.self_guardian.persister.SelfGuardianPersister.store_observation",
            new_callable=AsyncMock,
        ) as mock_store:
            with patch(
                "src.self_guardian.persister.SelfGuardianPersister.close",
                new_callable=AsyncMock,
            ) as mock_close:
                await store_observation(sample_observation)
                mock_store.assert_awaited_once_with(sample_observation)
                mock_close.assert_awaited_once()

    async def test_store_alert_convenience(
        self,
        sample_alert: SelfGuardianAlert,
    ):
        """The one-liner should create persister, store alert, and close."""
        with patch(
            "src.self_guardian.persister.SelfGuardianPersister.store_alert",
            new_callable=AsyncMock,
        ) as mock_store:
            with patch(
                "src.self_guardian.persister.SelfGuardianPersister.close",
                new_callable=AsyncMock,
            ) as mock_close:
                await store_alert(sample_alert)
                mock_store.assert_awaited_once_with(sample_alert)
                mock_close.assert_awaited_once()
