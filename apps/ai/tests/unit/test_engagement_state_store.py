"""Tests for engagement_state_store.py — PostgreSQL persistence bridge.

Verifies CRUD operations on EngagementState using a mocked asyncpg
connection.

Run:
    cd /home/aparna/Desktop/iterate_swarm/apps/ai
    uv run python -m pytest tests/unit/test_engagement_state_store.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.schemas.engagement_state import EngagementState


@pytest.fixture
def sample_state() -> EngagementState:
    """Create a minimal EngagementState for testing."""
    return EngagementState.create(
        engagement_id="eng-123",
        tenant_id="tenant-abc",
        workspace_mode="workspace",
        operator_goal="Test operator goal",
    )


@pytest.fixture
def mock_pg() -> MagicMock:
    """Mock asyncpg.connect to return a fake connection."""
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.close = AsyncMock(return_value=None)

    with patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = conn
        yield mock_connect


class TestEngagementStateStore:
    """Tests for EngagementStateStore CRUD operations."""

    def test_store_exists_and_importable(self):
        """The store module is importable and exposes the expected class."""
        from src.services.engagement_state_store import EngagementStateStore

        assert EngagementStateStore is not None
        assert hasattr(EngagementStateStore, "load_engagement_state")
        assert hasattr(EngagementStateStore, "save_engagement_state")
        assert hasattr(EngagementStateStore, "list_engagement_states")

    @pytest.mark.asyncio
    async def test_save_engagement_state_success(
        self, mock_pg: MagicMock, sample_state: EngagementState
    ):
        """save_engagement_state writes the state to PostgreSQL and returns None."""
        from src.services.engagement_state_store import EngagementStateStore

        store = EngagementStateStore()
        result = await store.save_engagement_state(sample_state)

        assert result is None
        mock_pg.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_engagement_state_calls_execute(
        self, mock_pg: MagicMock, sample_state: EngagementState
    ):
        """Verify the SQL INSERT/UPSERT was executed."""
        from src.services.engagement_state_store import EngagementStateStore

        store = EngagementStateStore()
        await store.save_engagement_state(sample_state)

        conn = mock_pg.return_value
        conn.execute.assert_called_once()
        call_args = conn.execute.call_args[0]
        assert "INSERT INTO" in call_args[0].upper() or "UPSERT" in call_args[0].upper()

    @pytest.mark.asyncio
    async def test_load_engagement_state_returns_state(self, mock_pg: MagicMock):
        """load_engagement_state returns an EngagementState when found."""
        from src.services.engagement_state_store import EngagementStateStore

        conn = mock_pg.return_value
        conn.fetchrow = AsyncMock(
            return_value={
                "engagement_id": "eng-123",
                "tenant_id": "tenant-abc",
                "workspace_mode": "workspace",
                "phase": "discovery",
                "operator_goal": "Test goal",
                "state_data": '{"discovery_notes": [], "ontology_objects": {}, "ontology_links": []}',
            }
        )

        store = EngagementStateStore()
        state = await store.load_engagement_state("eng-123")

        assert state is not None
        assert isinstance(state, EngagementState)
        assert state.engagement_id == "eng-123"
        assert state.tenant_id == "tenant-abc"
        assert state.workspace_mode == "workspace"
        mock_pg.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_engagement_state_returns_none_on_missing(self, mock_pg: MagicMock):
        """load_engagement_state returns None when no row is found."""
        from src.services.engagement_state_store import EngagementStateStore

        conn = mock_pg.return_value
        conn.fetchrow = AsyncMock(return_value=None)

        store = EngagementStateStore()
        state = await store.load_engagement_state("nonexistent")

        assert state is None

    @pytest.mark.asyncio
    async def test_list_engagement_states_returns_list(self, mock_pg: MagicMock):
        """list_engagement_states returns a list of EngagementState objects."""
        from src.services.engagement_state_store import EngagementStateStore

        conn = mock_pg.return_value
        conn.fetch = AsyncMock(
            return_value=[
                {
                    "engagement_id": "eng-1",
                    "tenant_id": "tenant-abc",
                    "workspace_mode": "workspace",
                    "phase": "discovery",
                    "operator_goal": "Goal 1",
                    "state_data": "{}",
                },
                {
                    "engagement_id": "eng-2",
                    "tenant_id": "tenant-abc",
                    "workspace_mode": "dashboard",
                    "phase": "ontology_mapping",
                    "operator_goal": "Goal 2",
                    "state_data": "{}",
                },
            ]
        )

        store = EngagementStateStore()
        states = await store.list_engagement_states("tenant-abc")

        assert len(states) == 2
        assert all(isinstance(s, EngagementState) for s in states)
        assert states[0].engagement_id == "eng-1"
        assert states[1].engagement_id == "eng-2"
        mock_pg.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_engagement_states_returns_empty_on_no_results(self, mock_pg: MagicMock):
        """list_engagement_states returns an empty list when no states exist."""
        from src.services.engagement_state_store import EngagementStateStore

        conn = mock_pg.return_value
        conn.fetch = AsyncMock(return_value=[])

        store = EngagementStateStore()
        states = await store.list_engagement_states("tenant-empty")

        assert states == []

    @pytest.mark.asyncio
    async def test_save_and_load_round_trip(
        self, mock_pg: MagicMock, sample_state: EngagementState
    ):
        """A state saved and then loaded should match (mocked)."""
        from src.services.engagement_state_store import EngagementStateStore

        conn = mock_pg.return_value

        store = EngagementStateStore()
        await store.save_engagement_state(sample_state)

        # Simulate the DB returning the saved data
        conn.fetchrow = AsyncMock(
            return_value={
                "engagement_id": sample_state.engagement_id,
                "tenant_id": sample_state.tenant_id,
                "workspace_mode": sample_state.workspace_mode,
                "phase": sample_state.phase,
                "operator_goal": sample_state.operator_goal,
                "state_data": '{}',
            }
        )

        loaded = await store.load_engagement_state(sample_state.engagement_id)

        assert loaded is not None
        assert loaded.engagement_id == sample_state.engagement_id
        assert loaded.tenant_id == sample_state.tenant_id
        assert loaded.workspace_mode == sample_state.workspace_mode
