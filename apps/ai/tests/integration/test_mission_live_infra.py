"""Real-infrastructure verification for the mission pipeline.

These tests are *not* mocks — they hit the live Docker services and a real LLM:

* :class:`TestMissionStateStoreLive` — writes/reads ``mission_state`` on the
  real ``iterateswarm-postgres`` container (DDL mirrored from Go core).
* :class:`TestMissionDecisionRealLlm` — gets a structured decision from Groq.

Both degrade to ``pytest.skip`` when the infra/LLM is absent, so the default
offline suite stays green and CI can gate these behind Docker+key presence.
"""
from __future__ import annotations

import os
import time
from typing import AsyncGenerator

import asyncpg
import pytest
from openai import APIConnectionError, APITimeoutError, RateLimitError
from pytest_asyncio import fixture as aio_fixture

from src.mission.decision import MissionDecision, MissionDecisionEngine
from src.mission.storage import MissionMetrics, MissionStateStore

# ── Suite classification ────────────────────────────────────────────────
# Live-model evaluation: requires provider credentials, incurs cost and
# latency, and is excluded from the deterministic gate via `-m "not llm"`.
pytestmark = pytest.mark.llm


pytestmark = [pytest.mark.integration]

# Connect to the real worker container (localhost:5433) by default; tests can
# override ITERATESWARM_DATABASE_URL for a different sandbox.
LIVE_DSN = os.environ.get(
    "ITERATESWARM_DATABASE_URL",
    "postgresql://iterateswarm:iterateswarm@localhost:5433/iterateswarm",
)

_TENANT = "integration-mission-live"

# Bounded retry for transient upstream (Groq network/timeout) failures, so the
# integration check stays honest on real errors but does not flakily fail on a
# single dropped connection to the external LLM provider.
_TRANSIENT = (APIConnectionError, APITimeoutError, RateLimitError)
_RETRIES = 3


def _retry_llm(call, *args, **kwargs):
    last_exc = None
    for attempt in range(_RETRIES):
        try:
            return call(*args, **kwargs)
        except _TRANSIENT as exc:
            last_exc = exc
            time.sleep(0.5 * (attempt + 1))
    raise last_exc


@aio_fixture
async def live_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    """Connect to the real Postgres; skip with a clear reason if it's down."""
    try:
        pool = await asyncpg.create_pool(LIVE_DSN, min_size=1, max_size=2, command_timeout=30)
    except Exception as exc:  # connection refused, auth, unknown host
        pytest.skip(f"Live Postgres not reachable at {LIVE_DSN}: {exc}")
    yield pool
    await pool.close()


@aio_fixture
async def store(live_pool: asyncpg.Pool) -> MissionStateStore:
    # Isolated table so the test never collides with the production
    # `mission_state` view managed by the Go core.
    store = MissionStateStore(live_pool, table_name="mission_state_live")
    await store.init_schema()
    await store.delete_tenant(_TENANT)  # idempotent test isolation
    return store


class TestMissionStateRealPostgres:
    """Real DDL + full round-trip persistence on the live container."""

    @pytest.mark.asyncio
    async def test_upsert_roundtrip(self, store: MissionStateStore) -> None:
        metrics = MissionMetrics(
            tenant_id=_TENANT,
            mrr=35000.0,
            burn_rate=12000.0,
            runway_days=18,
            trust_score=72,
            founder_focus="extend runway",
            active_alerts="burn_high",
            burn_alert=True,
            burn_severity="high",
            mrr_trend="+3.2%",
            churn_rate=2.1,
            error_spike=False,
            burn_multiple=2.9,
            effective_runway_days=18,
        )
        row_id = await store.save(metrics)
        assert row_id, "save() must return a generated row id"

        snapshot = await store.get_epoch(_TENANT)
        assert snapshot is not None, "row should be readable after write"
        assert float(snapshot["mrr"]) == pytest.approx(35000.0)
        assert int(snapshot["runway_days"]) == 18
        assert snapshot["burn_alert"] is True
        assert snapshot["tenant_id"] == _TENANT

    @pytest.mark.asyncio
    async def test_update_in_place(self, store: MissionStateStore) -> None:
        row_id = await store.save(MissionMetrics(tenant_id=_TENANT, mrr=10000.0))
        await store.save(MissionMetrics(tenant_id=_TENANT, mrr=14000.0), mission_id=row_id)

        snapshot = await store.get_epoch(_TENANT)
        assert snapshot is not None
        assert float(snapshot["mrr"]) == pytest.approx(14000.0)
        assert snapshot["id"] == row_id


class TestMissionDecisionEngine:
    """Real Groq decisioning with structured output parsing."""

    llm_available = bool(os.environ.get("GROQ_API_KEY"))

    @pytest.mark.skipif(not llm_available, reason="GROQ_API_KEY not in env")
    def test_decide_returns_typed_decision(self) -> None:
        engine = MissionDecisionEngine()
        decision = _retry_llm(
            engine.decide,
            objective="Reduce burn-rate to extend runway past 12 months",
            metrics=MissionMetrics(
                tenant_id=_TENANT,
                mrr=35000.0,
                burn_rate=12000.0,
                runway_days=18,
                trust_score=72,
                founder_focus="extend runway",
            ),
            asks=["prioritize highest-leverage spend reduction"],
        )

        assert isinstance(decision, MissionDecision)
        assert decision.status in {"ACTIVE", "STALLED", "COMPLETED", "FAILED"}
        assert 0.0 <= decision.confidence <= 1.0
        assert isinstance(decision.next_action, str) and decision.next_action
        assert isinstance(decision.reasoning, list)

    @pytest.mark.skipif(not llm_available, reason="GROQ_API_KEY not in env")
    def test_parse_defensive_on_malformed_json(self) -> None:
        from src.mission.decision import _parse_json

        assert _parse_json("still not json") == {}
        assert _parse_json('```json\n{"objective":"x","status":"ACTIVE"}\n```') == {
            "objective": "x",
            "status": "ACTIVE",
        }


# ─────────────────────────────────────────────────────────────────────
# Sprint 1 — Timeline + Versioning (additive tables, real Postgres)
# ─────────────────────────────────────────────────────────────────────
from src.mission.timeline import (  # noqa: E402
    MissionEventType,
    MissionSnapshotStore,
    MissionTimeline,
)

_TL_TABLE = "timeline_events_live"
_SNAP_TABLE = "mission_snapshots_live"


@pytest.fixture
async def mission_timeline(live_pool: asyncpg.Pool) -> MissionTimeline:
    log = MissionTimeline(live_pool, table=_TL_TABLE)
    await log.init_schema()
    async with live_pool.acquire() as conn:  # idempotent test isolation
        await conn.execute(f"DELETE FROM {_TL_TABLE}")
    return log


@pytest.fixture
async def snapshot_store(live_pool: asyncpg.Pool) -> MissionSnapshotStore:
    store = MissionSnapshotStore(live_pool, table=_SNAP_TABLE)
    await store.init_schema()
    async with live_pool.acquire() as conn:  # idempotent test isolation
        await conn.execute(f"DELETE FROM {_SNAP_TABLE}")
    return store


class TestMissionTimeline:
    """Append-only, versioned mission history on the live container."""

    @pytest.mark.asyncio
    async def test_append_versions_increment_per_mission(
        self, mission_timeline: MissionTimeline
    ) -> None:
        v1 = await mission_timeline.record(
            "m-tl-a", MissionEventType.STARTED, actor="ceo", source="workspace"
        )
        v2 = await mission_timeline.record(
            "m-tl-a", MissionEventType.CONFIDENCE_CHANGED, payload={"confidence": 71}
        )
        v3 = await mission_timeline.record(
            "m-tl-a", MissionEventType.COMPLETED, actor="ai-coo"
        )
        assert (v1, v2, v3) == (1, 2, 3)

        other = await mission_timeline.record("m-tl-b", MissionEventType.STARTED)
        assert other == 1  # version is per-entity

    @pytest.mark.asyncio
    async def test_history_is_append_ordered(
        self, mission_timeline: MissionTimeline
    ) -> None:
        await mission_timeline.record("m-tl-b", MissionEventType.CREATED)
        await mission_timeline.record("m-tl-b", MissionEventType.STARTED)
        await mission_timeline.record("m-tl-b", MissionEventType.CONFIDENCE_CHANGED)

        events = await mission_timeline.history("m-tl-b")
        assert [e.version for e in events] == [1, 2, 3]
        assert [e.event_type for e in events] == [
            "MISSION_CREATED",
            "MISSION_STARTED",
            "MISSION_CONFIDENCE_CHANGED",
        ]

    @pytest.mark.asyncio
    async def test_since_supports_forward_replay(
        self, mission_timeline: MissionTimeline
    ) -> None:
        await mission_timeline.record("m-tl-c", MissionEventType.STARTED)
        await mission_timeline.record("m-tl-c", MissionEventType.REVIEWED)
        tail = await mission_timeline.since("m-tl-c", 1)
        assert [e.version for e in tail] == [2]


class TestMissionSnapshots:
    """Instant-restore snapshots + mission diff on the live container."""

    @pytest.mark.asyncio
    async def test_capture_latest_and_diff(
        self, snapshot_store: MissionSnapshotStore
    ) -> None:
        v1 = await snapshot_store.capture(
            "m-snap-x", {"status": "ACTIVE", "confidence": 82, "runway_days": 18}
        )
        v2 = await snapshot_store.capture(
            "m-snap-x",
            {"status": "ACTIVE", "confidence": 71, "runway_days": 12, "blocker": "jira_stalled"},
        )

        latest = await snapshot_store.latest("m-snap-x")
        assert latest is not None
        assert latest["confidence"] == 71

        expected = await snapshot_store.at("m-snap-x", v1)
        assert expected is not None and expected["confidence"] == 82

        diff = await snapshot_store.diff("m-snap-x", newer=v2, older=v1)
        assert diff is not None
        assert diff["from_version"] == v1
        assert diff["to_version"] == v2
        assert diff["confidence_delta"] == -11
        assert {"confidence", "runway_days", "blocker"} <= set(diff["changed"])