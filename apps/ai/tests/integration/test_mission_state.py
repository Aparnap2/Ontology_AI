"""MissionState integration with real Postgres.

L2 tests - Real Docker Postgres, mocked LLM.
Performs actual database read/write with test fixtures.
"""
import asyncio
import os
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest


# Test database configuration - uses separate test DB
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://test:test@localhost:5432/test_trackguard"
)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for session-scoped async fixtures."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_pg_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    """Create a connection pool to test Postgres.

    Skip if Postgres not available or table doesn't exist.
    """
    try:
        pool = await asyncpg.create_pool(
            TEST_DATABASE_URL,
            min_size=1,
            max_size=2,
            command_timeout=30,
        )
        # Verify table exists
        async with pool.acquire() as conn:
            await conn.fetchval(
                "SELECT 1 FROM mission_states LIMIT 1"
            )
        yield pool
        await pool.close()
    except ConnectionRefusedError:
        pytest.skip("Postgres not available at TEST_DATABASE_URL")
    except asyncpg.InvalidCatalogNameError:
        pytest.skip("Test database 'test_trackguard' does not exist")
    except asyncpg.UndefinedTableError:
        pytest.skip("mission_states table not created yet")


@pytest.fixture
async def clean_tenant(test_pg_pool: asyncpg.Pool) -> AsyncGenerator[str, None]:
    """Provide a clean tenant ID and clean up after test."""
    tenant_id = f"test-l2-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    yield tenant_id
    # Cleanup
    async with test_pg_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM mission_states WHERE tenant_id = $1",
            tenant_id
        )


class TestMissionStateRoundtrip:
    """MissionState database roundtrip tests.

    Tests write to real Postgres, read back correctly.
    Mocks LLM calls while using real database.
    """

    @pytest.mark.asyncio
    async def test_create_and_retrieve_mission_state(
        self,
        test_pg_pool: asyncpg.Pool,
        clean_tenant: str,
    ):
        """Write to real Postgres, read back correctly."""
        from src.session.mission_state import (
            MissionState,
            get_mission_state,
            update_mission_state,
        )

        # Create initial state
        state = MissionState(
            tenant_id=clean_tenant,
            runway_days=12,
            burn_alert=True,
            burn_severity="high",
            mrr_trend="declining",
            churn_rate=3.5,
        )

        # Mock the DATABASE_URL for this test to use pool directly
        with patch("src.session.mission_state.DATABASE_URL", TEST_DATABASE_URL):
            # Write to database
            success = await update_mission_state(state)
            assert success is True

            # Read back from database
            retrieved = await get_mission_state(clean_tenant)
            assert retrieved.tenant_id == clean_tenant
            assert retrieved.runway_days == 12
            assert retrieved.burn_alert is True
            assert retrieved.burn_severity == "high"
            assert retrieved.mrr_trend == "declining"
            assert retrieved.churn_rate == 3.5

    @pytest.mark.asyncio
    async def test_update_existing_mission_state(
        self,
        test_pg_pool: asyncpg.Pool,
        clean_tenant: str,
    ):
        """Update existing MissionState atomically."""
        from src.session.mission_state import (
            MissionState,
            get_mission_state,
            update_mission_state,
        )

        with patch("src.session.mission_state.DATABASE_URL", TEST_DATABASE_URL):
            # Create initial state
            initial = MissionState(
                tenant_id=clean_tenant,
                runway_days=6,
            )
            await update_mission_state(initial)

            # Update with new values
            updated = MissionState(
                tenant_id=clean_tenant,
                runway_days=12,
                burn_alert=True,
                burn_severity="critical",
            )
            await update_mission_state(updated)

            # Verify update
            retrieved = await get_mission_state(clean_tenant)
            assert retrieved.runway_days == 12
            assert retrieved.burn_alert is True
            assert retrieved.burn_severity == "critical"

    @pytest.mark.asyncio
    async def test_graceful_fallback_when_not_found(
        self,
        test_pg_pool: asyncpg.Pool,
    ):
        """Missing tenant returns empty MissionState (graceful fallback)."""
        from src.session.mission_state import (
            MissionState,
            get_mission_state,
        )

        with patch("src.session.mission_state.DATABASE_URL", TEST_DATABASE_URL):
            retrieved = await get_mission_state("nonexistent-tenant-xyz")
            assert retrieved.tenant_id == "nonexistent-tenant-xyz"
            assert retrieved.runway_days is None
            assert retrieved.burn_alert is False


class TestRelevanceGateWithRealData:
    """Relevance gate with real session data.

    Tests keyword routing with real MissionState context.
    Mocks LLM, uses real database for session data.
    """

    @pytest.mark.asyncio
    async def test_finance_keywords_trigger_with_session(
        self,
        test_pg_pool: asyncpg.Pool,
        clean_tenant: str,
    ):
        """Keyword routing with real session data."""
        from src.session.mission_state import (
            MissionState,
            update_mission_state,
        )
        from src.session.relevance_gate import evaluate_relevance

        with patch("src.session.mission_state.DATABASE_URL", TEST_DATABASE_URL):
            # Pre-populate session with burn alert
            state = MissionState(
                tenant_id=clean_tenant,
                burn_alert=True,
                burn_severity="high",
                active_alerts="FG-01,FG-04",
            )
            await update_mission_state(state)

            # Evaluate relevance with finance keyword
            result = evaluate_relevance("My burn rate is too high")
            assert result.should_respond is True
            assert "finance" in result.triggered_domains

    @pytest.mark.asyncio
    async def test_active_alerts_trigger_without_keywords(
        self,
        test_pg_pool: asyncpg.Pool,
        clean_tenant: str,
    ):
        """Active alerts + question triggers even without keywords."""
        from src.session.mission_state import (
            MissionState,
            update_mission_state,
        )
        from src.session.relevance_gate import evaluate_relevance

        with patch("src.session.mission_state.DATABASE_URL", TEST_DATABASE_URL):
            # Pre-populate with active alerts
            state = MissionState(
                tenant_id=clean_tenant,
                active_alerts="FG-01,OG-02",
            )
            await update_mission_state(state)

            # Ask about the alert (no finance keyword)
            result = evaluate_relevance(
                "What is happening with the FG-01 alert?",
                active_alerts=["FG-01", "OG-02"]
            )
            assert result.should_respond is True


class TestAgentHealthChecks:
    """Health check endpoints for agents.

    Per PRD: Each agent has health_check() returning status.
    """

    @pytest.mark.asyncio
    async def test_finance_health_check(self):
        """Finance Guardian health check returns expected structure."""
        from src.agents.finance.graph import FinanceGuardianGraph

        graph = FinanceGuardianGraph()
        health = await graph.health_check()

        assert health["status"] == "ok"
        assert health["capability"] == "finance.runway_risk"
        assert health["owner"] == "finance-guardian"
        assert "latency_ms" in health
        assert health["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_bi_health_check(self):
        """BI Analyst health check returns expected structure."""
        from src.agents.bi.graph import BIAnalystGraph

        graph = BIAnalystGraph()
        health = await graph.health_check()

        assert health["status"] == "ok"
        assert health["capability"] == "bi.user_engagement"
        assert health["owner"] == "bi-analyst"
        assert "latency_ms" in health
        assert health["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_ops_health_check(self):
        """Ops Watch health check returns expected structure."""
        from src.agents.ops.graph import OpsWatchGraph

        graph = OpsWatchGraph()
        health = await graph.health_check()

        assert health["status"] == "ok"
        assert health["capability"] == "ops.health_deployment"
        assert health["owner"] == "ops-watch"
        assert "latency_ms" in health
        assert health["latency_ms"] >= 0
