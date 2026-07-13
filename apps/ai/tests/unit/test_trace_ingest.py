"""Trace Ingestion tests — pure Python, zero infra."""
from datetime import datetime, timedelta, timezone

from src.schemas.self_guardian import AgentObservation
from src.self_guardian.trace_ingest import TraceIngester, map_trace_to_observation


def _make_trace(overrides: dict | None = None) -> dict:
    base = {
        "id": "trace-abc-123",
        "name": "generate_investor_update",
        "user_id": "FP&A",
        "session_id": "session-456",
        "tags": ["finance", "investor_update", "tool:draft_investor_update", "agent:FP&A"],
        "input": "Generate investor update for Q2",
        "output": "Draft update ready",
        "start_time": "2026-07-08T10:00:00+00:00",
        "end_time": "2026-07-08T10:00:05+00:00",
        "status": "completed",
        "error": None,
        "observations": [
            {
                "id": "obs-1",
                "name": "llm_invoke",
                "type": "generation",
                "model": "gpt-4o",
                "start_time": "2026-07-08T10:00:00+00:00",
                "end_time": "2026-07-08T10:00:04+00:00",
                "input": "...",
                "output": "...",
                "level": "DEFAULT",
                "status": "completed",
                "metadata": {"tool_id": "draft_investor_update", "target": "investor_communications"},
            }
        ],
    }
    if overrides:
        base.update(overrides)
    return base


class TestMapTraceToObservation:
    def test_normal_trace(self):
        obs = map_trace_to_observation(_make_trace())
        assert obs is not None
        assert obs.agent_name == "FP&A"
        assert obs.action == "generate_investor_update"
        assert obs.tool_id == "draft_investor_update"
        assert obs.target_entity == "session-456"
        assert obs.trace_id == "trace-abc-123"
        assert obs.duration_ms == 5000
        assert obs.success is True
        assert obs.error_message is None

    def test_minimal_trace(self):
        trace = {"id": "minimal-1", "name": "ping", "status": "completed"}
        obs = map_trace_to_observation(trace)
        assert obs is not None
        assert obs.agent_name == "unknown"
        assert obs.action == "ping"
        assert obs.tool_id is None
        assert obs.duration_ms == 0
        assert obs.success is True

    def test_malformed_trace_returns_none(self):
        assert map_trace_to_observation({}) is None
        assert map_trace_to_observation(None) is None  # type: ignore[arg-type]
        assert map_trace_to_observation("not a dict") is None  # type: ignore[arg-type]
        assert map_trace_to_observation(42) is None  # type: ignore[arg-type]

    def test_agent_from_tags_fallback(self):
        trace = {"id": "t1", "name": "test", "tags": ["agent:OpsBot"], "status": "completed"}
        obs = map_trace_to_observation(trace)
        assert obs is not None
        assert obs.agent_name == "OpsBot"

    def test_tool_from_tags(self):
        trace = {"id": "t1", "name": "test", "tags": ["tool:flag_churn"], "status": "completed"}
        obs = map_trace_to_observation(trace)
        assert obs is not None
        assert obs.tool_id == "flag_churn"

    def test_tool_from_observation_metadata(self):
        trace = {
            "id": "t1",
            "name": "test",
            "status": "completed",
            "observations": [
                {"name": "ob1", "metadata": {"tool_id": "pause_payment"}}
            ],
        }
        obs = map_trace_to_observation(trace)
        assert obs is not None
        assert obs.tool_id == "pause_payment"

    def test_duration_calculation(self):
        trace = _make_trace({
            "start_time": "2026-07-08T10:00:00+00:00",
            "end_time": "2026-07-08T10:02:30+00:00",
        })
        obs = map_trace_to_observation(trace)
        assert obs is not None
        assert obs.duration_ms == 150000

    def test_success_from_status(self):
        trace = {"id": "t1", "name": "test", "status": "failed", "error": "timeout"}
        obs = map_trace_to_observation(trace)
        assert obs is not None
        assert obs.success is False
        assert obs.error_message == "timeout"

    def test_target_from_input_fallback(self):
        trace = {"id": "t1", "name": "test", "input": "customer email draft for Q3", "status": "completed"}
        obs = map_trace_to_observation(trace)
        assert obs is not None
        assert "customer email" in obs.target_entity

    def test_timestamp_parsing(self):
        trace = {"id": "t1", "name": "test", "start_time": "2026-01-15T08:30:00+00:00", "status": "completed"}
        obs = map_trace_to_observation(trace)
        assert obs is not None
        assert obs.timestamp.year == 2026
        assert obs.timestamp.month == 1
        assert obs.timestamp.hour == 8


class TestTraceIngester:
    def test_ingest_normal_trace(self):
        ingester = TraceIngester()
        obs = ingester.ingest_trace(_make_trace())
        assert obs is not None
        assert obs.trace_id == "trace-abc-123"

    def test_ingest_minimal_trace(self):
        ingester = TraceIngester()
        obs = ingester.ingest_trace({"id": "m1", "name": "ping", "status": "completed"})
        assert obs is not None
        assert obs.trace_id == "m1"

    def test_ingest_malformed_returns_none(self):
        ingester = TraceIngester()
        assert ingester.ingest_trace({}) is None
        assert ingester.ingest_trace(None) is None  # type: ignore[arg-type]

    def test_dedup_same_trace_id(self):
        ingester = TraceIngester(dedup_window_minutes=60)
        trace = _make_trace()
        first = ingester.ingest_trace(trace)
        second = ingester.ingest_trace(trace)
        assert first is not None
        assert second is None

    def test_dedup_outside_window(self):
        ingester = TraceIngester(dedup_window_minutes=0)
        trace = _make_trace()
        first = ingester.ingest_trace(trace)
        second = ingester.ingest_trace(trace)
        assert first is not None
        assert second is not None

    def test_get_stats_after_ingest(self):
        ingester = TraceIngester()
        ingester.ingest_trace(_make_trace())
        ingester.ingest_trace(_make_trace({"id": "trace-xyz-789"}))
        ingester.ingest_trace({})
        stats = ingester.get_stats()
        assert stats["total_ingested"] == 2
        assert stats["total_failed"] == 1
        assert stats["total_deduped"] == 0
        assert stats["last_ingest_time"] is not None

    def test_stats_dedup_counted(self):
        ingester = TraceIngester(dedup_window_minutes=60)
        ingester.ingest_trace(_make_trace())
        ingester.ingest_trace(_make_trace())
        stats = ingester.get_stats()
        assert stats["total_ingested"] == 1
        assert stats["total_deduped"] == 1

    def test_collector_receives_observation(self):
        from src.self_guardian.monitor import ObservationCollector

        collector = ObservationCollector()
        ingester = TraceIngester(collector=collector)
        ingester.ingest_trace(_make_trace())
        assert collector.count == 1
        obs = collector.get_observations()
        assert obs[0].trace_id == "trace-abc-123"

    def test_multi_agent_ingest(self):
        ingester = TraceIngester()
        t1 = _make_trace({"id": "t1", "user_id": "FP&A", "name": "calculate_mrr"})
        t2 = _make_trace({"id": "t2", "user_id": "Ops Bot", "name": "check_usage"})
        o1 = ingester.ingest_trace(t1)
        o2 = ingester.ingest_trace(t2)
        assert o1 is not None
        assert o2 is not None
        assert o1.agent_name == "FP&A"
        assert o2.agent_name == "Ops Bot"
