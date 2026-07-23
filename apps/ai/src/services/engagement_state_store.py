"""EngagementState persistence bridge — PostgreSQL backend (PRD §14.3).

Provides CRUD operations for ``EngagementState`` objects stored in PostgreSQL.
The state is serialised as JSONB for the flexible patch fields and indexed by
``engagement_id`` + ``tenant_id`` for efficient listing.

Usage:
    from src.services.engagement_state_store import EngagementStateStore
    from src.schemas.engagement_state import EngagementState

    store = EngagementStateStore()

    # Save
    state = EngagementState.create(engagement_id="e1", tenant_id="t1", workspace_mode="workspace")
    store.save_engagement_state(state)

    # Load
    loaded = store.load_engagement_state("e1")

    # List by tenant
    states = store.list_engagement_states("t1")
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import asyncpg

from src.schemas.engagement_state import EngagementState

log = logging.getLogger(__name__)

_DEFAULT_DSN = "postgresql://localhost:5432/iterateswarm"


def _get_dsn() -> str:
    return os.environ.get("ITERATESWARM_DATABASE_URL", _DEFAULT_DSN)


class EngagementStateStore:
    """PostgreSQL persistence bridge for ``EngagementState`` objects.

    Each state is stored in a dedicated ``engagement_states`` table with
    the schema::

        engagement_id  TEXT PRIMARY KEY,
        tenant_id      TEXT NOT NULL,
        workspace_mode TEXT NOT NULL,
        phase          TEXT NOT NULL,
        operator_goal  TEXT,
        state_data     JSONB NOT NULL,
        updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()

    ``state_data`` holds all list and dict fields (discovery_notes,
    ontology_objects, truth_findings, etc.) as a JSON blob so the schema
    stays stable as V5.1 evolves.
    """

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn or _get_dsn()

    async def _connect(self) -> asyncpg.Connection:
        """Open a new PostgreSQL connection."""
        return await asyncpg.connect(self._dsn)

    @staticmethod
    def _to_db_row(state: EngagementState) -> dict:
        """Serialize an ``EngagementState`` into a DB row dict."""
        dumped = state.model_dump()
        # Extract top-level columns
        state_data = {k: v for k, v in dumped.items() if k not in (
            "engagement_id",
            "tenant_id",
            "workspace_mode",
            "phase",
            "operator_goal",
            "updated_at",
        )}
        return {
            "engagement_id": dumped["engagement_id"],
            "tenant_id": dumped["tenant_id"],
            "workspace_mode": dumped["workspace_mode"],
            "phase": dumped["phase"],
            "operator_goal": dumped.get("operator_goal"),
            "state_data": json.dumps(state_data),
        }

    @staticmethod
    def _from_db_row(row: dict) -> EngagementState:
        """Reconstruct an ``EngagementState`` from a DB row dict."""
        state_data = {}
        if row.get("state_data"):
            state_data = json.loads(row["state_data"]) if isinstance(row["state_data"], str) else row["state_data"]
        return EngagementState(
            engagement_id=row["engagement_id"],
            tenant_id=row["tenant_id"],
            workspace_mode=row["workspace_mode"],
            phase=row["phase"],
            operator_goal=row.get("operator_goal"),
            **state_data,
        )

    # ── CRUD ─────────────────────────────────────────────────────────────

    async def save_engagement_state(self, state: EngagementState) -> None:
        """Upsert an ``EngagementState`` into PostgreSQL.

        Uses ``INSERT ... ON CONFLICT (engagement_id) DO UPDATE`` so
        repeated saves are idempotent.
        """
        row = self._to_db_row(state)
        conn = await self._connect()
        try:
            await conn.execute(
                """
                INSERT INTO engagement_states
                    (engagement_id, tenant_id, workspace_mode, phase,
                     operator_goal, state_data, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, NOW())
                ON CONFLICT (engagement_id) DO UPDATE SET
                    tenant_id      = EXCLUDED.tenant_id,
                    workspace_mode = EXCLUDED.workspace_mode,
                    phase          = EXCLUDED.phase,
                    operator_goal  = EXCLUDED.operator_goal,
                    state_data     = EXCLUDED.state_data,
                    updated_at     = NOW()
                """,
                row["engagement_id"],
                row["tenant_id"],
                row["workspace_mode"],
                row["phase"],
                row["operator_goal"],
                row["state_data"],
            )
        finally:
            await conn.close()

    async def load_engagement_state(self, engagement_id: str) -> Optional[EngagementState]:
        """Load a single ``EngagementState`` by ``engagement_id``.

        Returns ``None`` if no matching row exists.
        """
        conn = await self._connect()
        try:
            row = await conn.fetchrow(
                "SELECT * FROM engagement_states WHERE engagement_id = $1",
                engagement_id,
            )
            if row is None:
                return None
            return self._from_db_row(dict(row))
        finally:
            await conn.close()

    async def list_engagement_states(self, tenant_id: str) -> list[EngagementState]:
        """List all ``EngagementState`` objects for a given ``tenant_id``.

        Returns an empty list if no states exist for the tenant.
        """
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                "SELECT * FROM engagement_states WHERE tenant_id = $1 ORDER BY updated_at DESC",
                tenant_id,
            )
            return [self._from_db_row(dict(r)) for r in rows]
        finally:
            await conn.close()
