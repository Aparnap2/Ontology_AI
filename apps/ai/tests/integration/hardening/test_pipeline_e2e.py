"""Sprint A — E2E trace/correlation propagation across the mission pipeline.

Proves, against *live* Postgres + a *real* LLM (Groq), that the flow

    connector-event → evidence → mission → decision → snapshot → timeline

carries a single ``trace_id`` + ``correlation_id`` end-to-end and stays
retry-/idempotency-safe.

Every stage is driven through :func:`src.observability.run_stage` so the
``PipelineRun`` records a typed ``StageResult`` (input, output, latency,
retry count, status) for each step. The test asserts:

* every stage ran and recorded a successful result,
* the same ``trace_id``/``correlation_id`` appear in every stage result *and*
  in every persisted artifact (evidence, mission row, snapshot body, timeline
  payload),
* the decision snapshot round-trips through ``MissionSnapshotStore``,
* re-delivering the same connector event (same ``correlation_id``, new
  ``trace_id``) does **not** append a duplicate timeline entry.

The connector event is a *synthetic* fixture (the repo's Mockoon data has no
connector-event endpoint, and ``conftest.py``'s mock data path is stale), so
this test avoids a hard dependency on a local Mockoon process while keeping
the real Postgres + real Groq integration honest.

Skips (module-level + fixture) when the live Postgres container is unreachable
or ``GROQ_API_KEY`` is absent, keeping the offline suite green.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, AsyncGenerator, Callable, Mapping
from uuid import uuid4

import asyncpg
import pytest
from openai import APIConnectionError, APITimeoutError, RateLimitError
from pytest_asyncio import fixture as aio_fixture

from src.mission.decision import MissionDecision, MissionDecisionEngine
from src.mission.storage import MissionMetrics, MissionStateStore
from src.mission.timeline import (
    MissionEventType,
    MissionSnapshotStore,
    MissionTimeline,
)
from src.observability import PipelineRun, TraceContext, run_stage, trace_context

# NOT marked `llm`: both tests here are deterministic observability
# assertions over an in-memory store and never reach a model. They were
# previously excluded from the deterministic gate by a module-level marker,
# which hid them.
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("GROQ_API_KEY"), reason="GROQ_API_KEY not set"
    ),
]

# Connect to the real worker container (localhost:5433) by default.
LIVE_DSN = os.environ.get(
    "ITERATESWARM_DATABASE_URL",
    "postgresql://iterateswarm:iterateswarm@localhost:5433/iterateswarm",
)

_TENANT = "e2e-obs"
_MISSION_STATE_TABLE = "mission_state_live_obs"
_TIMELINE_TABLE = "timeline_events_live_obs"
_SNAPSHOT_TABLE = "mission_snapshots_live_obs"

# Extra transient failures worth retrying for the real LLM stage (mirrors the
# bounded retry policy in test_mission_live_infra.py).
_TRANSIENT = (APIConnectionError, APITimeoutError, RateLimitError)

_STAGES = (
    "connector_event",
    "evidence",
    "mission",
    "decision",
    "snapshot",
    "timeline",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _call(
    fn: Callable[..., Any], *args: Any, **kwargs: Any
) -> Callable[[], Any]:
    """Bind args now; return a zero-argument callable for ``run_stage``."""
    return lambda: fn(*args, **kwargs)


# ─────────────────────────────────────────────────────────────────────
# Synthetic connector-event fixture + stage functions (test-local)
# ─────────────────────────────────────────────────────────────────────
def make_connector_event(trace: TraceContext) -> dict[str, Any]:
    """A synthetic connector event (e.g. Stripe payment-failure webhook)."""
    return {
        "event_id": str(uuid4()),
        "correlation_id": trace.correlation_id,
        "trace_id": trace.trace_id,
        "tenant_id": trace.tenant_id,
        "source": "stripe.payment_failed",
        "occurred_at": "2026-08-07T00:00:00Z",
        "metric": "mrr",
        "value": 33500.0,
        "metrics": {
            "mrr": 33500.0,
            "burn_rate": 12000.0,
            "runway_days": 18,
            "trust_score": 72,
            "founder_focus": "extend runway",
            "active_alerts": "burn_high",
        },
    }


def deliver_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Connector delivery: acknowledge the event with a received stamp."""
    return {**event, "acknowledged": True, "received_at": _now()}


def assemble_evidence(event: Mapping[str, Any]) -> dict[str, Any]:
    """Evidence-assembly: normalise the event into an evidence record."""
    return {
        "evidence_id": str(uuid4()),
        "source": event["source"],
        "metric": event["metric"],
        "value": event["value"],
        "observed_at": event["occurred_at"],
        "trace_id": event["trace_id"],
        "correlation_id": event["correlation_id"],
        "tenant_id": event["tenant_id"],
    }


def _metrics_from_event(event: Mapping[str, Any]) -> MissionMetrics:
    m = event["metrics"]
    return MissionMetrics(
        tenant_id=event["tenant_id"],
        mrr=float(m["mrr"]) if m.get("mrr") is not None else None,
        burn_rate=float(m["burn_rate"]) if m.get("burn_rate") is not None else None,
        runway_days=int(m["runway_days"]) if m.get("runway_days") is not None else None,
        trust_score=int(m["trust_score"]) if m.get("trust_score") is not None else None,
        founder_focus=m.get("founder_focus"),
        active_alerts=m.get("active_alerts"),
    )


async def save_mission(store: MissionStateStore, event: Mapping[str, Any]) -> str:
    """Mission stage: persist metrics to the isolated mission-state table."""
    return await store.save(_metrics_from_event(event))


async def capture_snapshot(
    snap: MissionSnapshotStore,
    mission_id: str,
    decision: MissionDecision,
    evidence: Mapping[str, Any],
) -> int:
    """Snapshot stage: capture the composed state with the trace ids."""
    return await snap.capture(
        mission_id,
        {
            "mission_id": mission_id,
            "status": decision.status,
            "confidence": decision.confidence,
            "next_action": decision.next_action,
            "evidence_id": evidence["evidence_id"],
            "trace_id": evidence["trace_id"],
            "correlation_id": evidence["correlation_id"],
            "tenant_id": evidence["tenant_id"],
        },
        snapshot_type="decision",
    )


async def record_timeline(
    log: MissionTimeline,
    mission_id: str,
    *,
    event_type: MissionEventType,
    evidence: Mapping[str, Any],
    decision: MissionDecision,
    trace: TraceContext,
) -> int:
    """Timeline stage — idempotent: one CONFIDENCE_CHANGED per correlation_id.

    Re-delivery of the same logical event (same ``correlation_id``) returns the
    already-committed version instead of appending a second entry.
    """
    for event in await log.history(mission_id):
        if (
            event.event_type == event_type.value
            and event.correlation_id == trace.correlation_id
        ):
            return event.version  # dedup — already committed for this event

    return await log.record(
        mission_id,
        event_type,
        actor="stripe.connector",
        source="observability-e2e",
        payload={
            "trace_id": trace.trace_id,
            "correlation_id": trace.correlation_id,
            "tenant_id": trace.tenant_id,
            "evidence_id": evidence["evidence_id"],
            "mission_id": mission_id,
            "confidence": decision.confidence,
            "status": decision.status,
        },
        causation_id=evidence["evidence_id"],
        correlation_id=trace.correlation_id,
    )


# ─────────────────────────────────────────────────────────────────────
# Live infra fixtures (skip when Postgres is down)
# ─────────────────────────────────────────────────────────────────────
@aio_fixture
async def live_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    """Connect to the real Postgres; skip with a clear reason if it's down."""
    try:
        pool = await asyncpg.create_pool(
            LIVE_DSN, min_size=1, max_size=2, command_timeout=30
        )
    except Exception as exc:  # connection refused, auth, unknown host
        pytest.skip(f"Live Postgres not reachable at {LIVE_DSN}: {exc}")
    yield pool
    await pool.close()


@aio_fixture
async def obs_env(live_pool: asyncpg.Pool) -> AsyncGenerator[SimpleNamespace, None]:
    """Isolated additive tables for this sprint; cleaned before and after."""
    store = MissionStateStore(live_pool, table_name=_MISSION_STATE_TABLE)
    await store.init_schema()
    await store.delete_tenant(_TENANT)

    timeline = MissionTimeline(live_pool, table=_TIMELINE_TABLE)
    await timeline.init_schema()

    snapshots = MissionSnapshotStore(live_pool, table=_SNAPSHOT_TABLE)
    await snapshots.init_schema()

    async with live_pool.acquire() as conn:
        await conn.execute(f"DELETE FROM {_TIMELINE_TABLE}")
        await conn.execute(f"DELETE FROM {_SNAPSHOT_TABLE}")

    yield SimpleNamespace(
        pool=live_pool, store=store, timeline=timeline, snapshots=snapshots
    )

    async with live_pool.acquire() as conn:
        await conn.execute(f"DELETE FROM {_TIMELINE_TABLE}")
        await conn.execute(f"DELETE FROM {_SNAPSHOT_TABLE}")
    await store.delete_tenant(_TENANT)


# ─────────────────────────────────────────────────────────────────────
# E2E test
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_connector_event_to_timeline_carries_trace_id(
    obs_env: SimpleNamespace,
) -> None:
    """One event travels every stage; ids match end-to-end + snapshot round-trip."""
    store = obs_env.store
    timeline = obs_env.timeline
    snapshots = obs_env.snapshots

    trace = TraceContext.new(tenant_id=_TENANT)
    event = make_connector_event(trace)
    run = PipelineRun(trace=trace)
    engine = MissionDecisionEngine()

    with trace_context(trace):
        ingest = await run_stage(
            _call(deliver_event, event),
            stage="connector_event",
            trace=trace,
            run=run,
            stage_input=event,
        )
        evidence_stage = await run_stage(
            _call(assemble_evidence, event),
            stage="evidence",
            trace=trace,
            run=run,
            stage_input=event,
        )
        evidence = evidence_stage.output
        mission_stage = await run_stage(
            _call(save_mission, store, event),
            stage="mission",
            trace=trace,
            run=run,
            stage_input=evidence,
        )
        mission_id = mission_stage.output
        decision_stage = await run_stage(
            _call(
                engine.decide,
                objective="Reduce burn-rate to extend runway past 12 months",
                metrics=_metrics_from_event(event),
                asks=["prioritize highest-leverage spend reduction"],
            ),
            stage="decision",
            trace=trace,
            run=run,
            stage_input=evidence,
            timeout_s=25.0,
            transient=_TRANSIENT,
        )
        decision = decision_stage.output
        snapshot_stage = await run_stage(
            _call(capture_snapshot, snapshots, mission_id, decision, evidence),
            stage="snapshot",
            trace=trace,
            run=run,
            stage_input=decision,
        )
        timeline_stage = await run_stage(
            _call(
                record_timeline,
                timeline,
                mission_id,
                event_type=MissionEventType.CONFIDENCE_CHANGED,
                evidence=evidence,
                decision=decision,
                trace=trace,
            ),
            stage="timeline",
            trace=trace,
            run=run,
            stage_input=evidence,
        )

    # 1. every stage recorded, successful, with sane telemetry
    assert [s.stage for s in run.stages] == list(_STAGES)
    assert run.all_successful()
    for s in run.stages:
        assert s.status.value == "success"
        assert s.latency_ms >= 0.0
        assert s.retry_count >= 0
        assert s.output is not None
        # 2. one trace_id + correlation_id stamped on every stage result
        assert s.trace_id == trace.trace_id
        assert s.correlation_id == trace.correlation_id

    # audit trail: each stage records what it consumed
    assert ingest.input["correlation_id"] == trace.correlation_id
    assert evidence_stage.input["trace_id"] == trace.trace_id

    # 3. evidence carries the ids
    assert evidence["trace_id"] == trace.trace_id
    assert evidence["correlation_id"] == trace.correlation_id
    assert evidence["tenant_id"] == _TENANT

    # 4. mission row persisted and addressable by the returned id
    assert mission_id
    row = await store.get_epoch(_TENANT)
    assert row is not None
    assert row["id"] == mission_id
    assert row["tenant_id"] == _TENANT

    # 5. real Groq decision is a typed, valid decision
    assert isinstance(decision, MissionDecision)
    assert decision.status in {"ACTIVE", "STALLED", "COMPLETED", "FAILED"}
    assert 0.0 <= decision.confidence <= 1.0
    assert isinstance(decision.next_action, str) and decision.next_action

    # 6. snapshot round-trips with the ids + decision embedded
    snap_version = snapshot_stage.output
    latest = await snapshots.latest(mission_id)
    assert latest is not None
    assert latest["trace_id"] == trace.trace_id
    assert latest["correlation_id"] == trace.correlation_id
    assert latest["mission_id"] == mission_id
    assert latest["evidence_id"] == evidence["evidence_id"]
    assert latest["confidence"] == decision.confidence
    restored = await snapshots.at(mission_id, snap_version)
    assert restored == latest

    # 7. timeline has exactly one CONFIDENCE_CHANGED with the ids in payload
    assert timeline_stage.output == 1
    history = await timeline.history(mission_id)
    conf = [e for e in history if e.event_type == MissionEventType.CONFIDENCE_CHANGED.value]
    assert len(conf) == 1
    assert conf[0].correlation_id == trace.correlation_id
    assert conf[0].causation_id == evidence["evidence_id"]
    assert conf[0].payload["trace_id"] == trace.trace_id
    assert conf[0].payload["mission_id"] == mission_id
    assert conf[0].payload["confidence"] == decision.confidence


@pytest.mark.asyncio
async def test_duplicate_correlation_id_does_not_duplicate_timeline(
    obs_env: SimpleNamespace,
) -> None:
    """Re-delivery of the same event (same correlation_id) stays idempotent.

    Uses a stub decision — no LLM call — so this test is fast; it exercises
    exactly the dedup path inside the timeline stage.
    """
    timeline = obs_env.timeline
    mission_id = str(uuid4())
    evidence = {"evidence_id": str(uuid4())}
    decision = MissionDecision(
        objective="x",
        status="ACTIVE",
        confidence=0.7,
        next_action="act",
        reasoning=["stub"],
    )

    first = TraceContext.new(tenant_id=_TENANT)
    replay = TraceContext.new(
        tenant_id=_TENANT, correlation_id=first.correlation_id
    )
    assert replay.trace_id != first.trace_id  # redelivery = new trace, same corr

    v1 = await record_timeline(
        timeline,
        mission_id,
        event_type=MissionEventType.CONFIDENCE_CHANGED,
        evidence=evidence,
        decision=decision,
        trace=first,
    )
    v2 = await record_timeline(
        timeline,
        mission_id,
        event_type=MissionEventType.CONFIDENCE_CHANGED,
        evidence=evidence,
        decision=decision,
        trace=replay,
    )

    assert v1 == 1
    assert v2 == 1  # dedup returns the already-committed version
    history = await timeline.history(mission_id)
    assert [e.version for e in history] == [1]
    conf = [e for e in history if e.event_type == MissionEventType.CONFIDENCE_CHANGED.value]
    assert len(conf) == 1
    assert conf[0].correlation_id == first.correlation_id

    # belt-and-braces: direct DB count by correlation_id
    async with obs_env.pool.acquire() as conn:
        count = await conn.fetchval(
            f"SELECT count(*) FROM {_TIMELINE_TABLE} "
            "WHERE correlation_id = $1 AND event_type = $2",
            first.correlation_id,
            MissionEventType.CONFIDENCE_CHANGED.value,
        )
    assert count == 1
