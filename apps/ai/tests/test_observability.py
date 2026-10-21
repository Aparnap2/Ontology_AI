"""Tests for structured execution trace module.

All tests are pure in-memory — no I/O, no LLM, no wall clock dependencies.
"""

from __future__ import annotations

import json
from datetime import datetime as dt

import pytest
from pydantic import ValidationError

from src.mission.observability import ExecutionTrace, LLMCallRecord, TraceSpan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trace(tid: str = "t1") -> ExecutionTrace:
    return ExecutionTrace(trace_id=tid)


def _get(trace: ExecutionTrace, span_id: str) -> TraceSpan:
    """Lookup a span and assert it exists (narrows Optional for test clarity)."""
    span = trace.get_span(span_id)
    assert span is not None, f"expected span {span_id} to exist"
    return span


# ---------------------------------------------------------------------------
# 1. Trace records spans in order
# ---------------------------------------------------------------------------


class TestSpanOrdering:
    def test_spans_appended_in_call_order(self) -> None:
        trace = _make_trace()
        trace.start_span("first")
        trace.start_span("second")
        trace.start_span("third")

        names = [s.name for s in trace.spans]
        assert names == ["first", "second", "third"]

    def test_single_span(self) -> None:
        trace = _make_trace()
        sid = trace.start_span("solo")
        assert len(trace.spans) == 1
        assert trace.spans[0].span_id == sid


# ---------------------------------------------------------------------------
# 2. Parent-child relationships work
# ---------------------------------------------------------------------------


class TestParentChild:
    def test_child_references_parent(self) -> None:
        trace = _make_trace()
        parent_id = trace.start_span("parent")
        child_id = trace.start_span("child", parent=parent_id)

        child = _get(trace, child_id)
        assert child.parent_span_id == parent_id

    def test_root_span_has_no_parent(self) -> None:
        trace = _make_trace()
        sid = trace.start_span("root")
        span = _get(trace, sid)
        assert span.parent_span_id is None

    def test_multiple_children_same_parent(self) -> None:
        trace = _make_trace()
        pid = trace.start_span("parent")
        c1 = trace.start_span("c1", parent=pid)
        c2 = trace.start_span("c2", parent=pid)
        c3 = trace.start_span("c3", parent=pid)

        for cid in (c1, c2, c3):
            child = _get(trace, cid)
            assert child.parent_span_id == pid


# ---------------------------------------------------------------------------
# 3. LLM call records are captured
# ---------------------------------------------------------------------------


class TestLLMCallRecord:
    def test_record_captured_on_span(self) -> None:
        trace = _make_trace()
        sid = trace.start_span("llm.investigation")
        trace.llm_call_record(
            sid,
            model="gpt-4o",
            prompt_version="v2.1",
            input_tokens=120,
            output_tokens=45,
            latency_ms=320.5,
            decision="escalate",
        )
        span = _get(trace, sid)
        rec = span.attributes["llm_call"]
        assert rec["model"] == "gpt-4o"
        assert rec["prompt_version"] == "v2.1"
        assert rec["input_tokens"] == 120
        assert rec["output_tokens"] == 45
        assert rec["latency_ms"] == 320.5
        assert rec["decision"] == "escalate"

    def test_multiple_llm_calls_on_different_spans(self) -> None:
        trace = _make_trace()
        s1 = trace.start_span("llm.a")
        s2 = trace.start_span("llm.b")
        trace.llm_call_record(s1, "m1", "v1", 10, 5, 100.0, "yes")
        trace.llm_call_record(s2, "m2", "v2", 20, 8, 200.0, "no")

        r1 = _get(trace, s1).attributes["llm_call"]
        r2 = _get(trace, s2).attributes["llm_call"]
        assert r1["model"] == "m1"
        assert r2["model"] == "m2"

    def test_llm_record_with_zero_tokens(self) -> None:
        trace = _make_trace()
        sid = trace.start_span("llm.empty")
        trace.llm_call_record(sid, "m", "v", 0, 0, 0.0, "skip")
        rec = _get(trace, sid).attributes["llm_call"]
        assert rec["input_tokens"] == 0
        assert rec["output_tokens"] == 0


# ---------------------------------------------------------------------------
# 4. Timeline export is sorted by time
# ---------------------------------------------------------------------------


class TestTimeline:
    def test_timeline_sorted_by_start_time(self) -> None:
        trace = _make_trace()
        trace.start_span("third")
        trace.start_span("first")
        trace.start_span("second")

        timeline = trace.to_timeline()
        times = [t["start_time"] for t in timeline]
        assert times == sorted(times)

    def test_timeline_returns_dicts(self) -> None:
        trace = _make_trace()
        sid = trace.start_span("x")
        timeline = trace.to_timeline()
        assert len(timeline) == 1
        assert isinstance(timeline[0], dict)
        assert timeline[0]["span_id"] == sid

    def test_empty_trace_timeline(self) -> None:
        trace = _make_trace()
        assert trace.to_timeline() == []

    def test_timeline_preserves_all_fields(self) -> None:
        trace = _make_trace()
        sid = trace.start_span("evt", foo="bar")
        trace.end_span(sid, "ok")
        trace.add_event(sid, "note", detail="x")
        timeline = trace.to_timeline()
        entry = timeline[0]
        assert entry["name"] == "evt"
        assert entry["attributes"]["foo"] == "bar"
        assert entry["status"] == "ok"
        assert len(entry["events"]) == 1
        assert entry["events"][0]["name"] == "note"


# ---------------------------------------------------------------------------
# 5. Span status tracks ok/error/cancelled
# ---------------------------------------------------------------------------


class TestSpanStatus:
    def test_default_status_is_ok(self) -> None:
        trace = _make_trace()
        sid = trace.start_span("s")
        span = _get(trace, sid)
        assert span.status == "ok"

    def test_end_span_sets_ok(self) -> None:
        trace = _make_trace()
        sid = trace.start_span("s")
        trace.end_span(sid, "ok")
        assert _get(trace, sid).status == "ok"

    def test_end_span_sets_error(self) -> None:
        trace = _make_trace()
        sid = trace.start_span("s")
        trace.end_span(sid, "error")
        assert _get(trace, sid).status == "error"

    def test_end_span_sets_cancelled(self) -> None:
        trace = _make_trace()
        sid = trace.start_span("s")
        trace.end_span(sid, "cancelled")
        assert _get(trace, sid).status == "cancelled"

    def test_end_span_missing_raises(self) -> None:
        trace = _make_trace()
        with pytest.raises(KeyError, match="span not found"):
            trace.end_span("nonexistent")


# ---------------------------------------------------------------------------
# 6. Events within spans are recorded
# ---------------------------------------------------------------------------


class TestEvents:
    def test_event_added_to_span(self) -> None:
        trace = _make_trace()
        sid = trace.start_span("s")
        trace.add_event(sid, "retry", attempt=2)
        span = _get(trace, sid)
        assert len(span.events) == 1
        assert span.events[0]["name"] == "retry"
        assert span.events[0]["attempt"] == 2
        assert "timestamp" in span.events[0]

    def test_multiple_events_on_same_span(self) -> None:
        trace = _make_trace()
        sid = trace.start_span("s")
        trace.add_event(sid, "e1", a=1)
        trace.add_event(sid, "e2", b=2)
        trace.add_event(sid, "e3", c=3)
        span = _get(trace, sid)
        assert len(span.events) == 3
        assert [e["name"] for e in span.events] == ["e1", "e2", "e3"]

    def test_event_on_missing_span_raises(self) -> None:
        trace = _make_trace()
        with pytest.raises(KeyError, match="span not found"):
            trace.add_event("ghost", "evt")


# ---------------------------------------------------------------------------
# 7. Trace survives multiple concurrent spans
# ---------------------------------------------------------------------------


class TestConcurrentSpans:
    def test_many_open_spans(self) -> None:
        trace = _make_trace()
        ids = [trace.start_span(f"span_{i}") for i in range(50)]
        assert len(trace.spans) == 50
        # close them in reverse
        for sid in reversed(ids):
            trace.end_span(sid)
        assert all(s.end_time is not None for s in trace.spans)

    def test_interleaved_start_end(self) -> None:
        trace = _make_trace()
        s1 = trace.start_span("a")
        s2 = trace.start_span("b")
        trace.end_span(s1)
        s3 = trace.start_span("c")
        trace.end_span(s2)
        trace.end_span(s3)

        assert _get(trace, s1).end_time is not None
        assert _get(trace, s2).end_time is not None
        assert _get(trace, s3).end_time is not None
        assert len(trace.spans) == 3

    def test_get_span_missing_returns_none(self) -> None:
        trace = _make_trace()
        assert trace.get_span("nope") is None


# ---------------------------------------------------------------------------
# 8. All models strict (extra=forbid)
# ---------------------------------------------------------------------------


class TestModelStrictness:
    def test_trace_span_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            TraceSpan(
                span_id="x",
                parent_span_id=None,
                trace_id="t",
                name="n",
                start_time="2026-01-01T00:00:00Z",
                status="ok",
                bogus_field="nope",  # type: ignore[arg-type]
            )

    def test_llm_call_record_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            LLMCallRecord(
                model="m",
                prompt_version="v",
                input_tokens=0,
                output_tokens=0,
                latency_ms=0.0,
                decision="d",
                bad_field=1,  # type: ignore[arg-type]
            )

    def test_trace_span_strict_types(self) -> None:
        """span_id must be str, not int."""
        with pytest.raises(ValidationError):
            TraceSpan(
                span_id=123,  # type: ignore[arg-type]
                parent_span_id=None,
                trace_id="t",
                name="n",
                start_time="2026-01-01T00:00:00Z",
            )

    def test_llm_call_record_strict_types(self) -> None:
        """input_tokens must be int, not str."""
        with pytest.raises(ValidationError):
            LLMCallRecord(
                model="m",
                prompt_version="v",
                input_tokens="abc",  # type: ignore[arg-type]
                output_tokens=0,
                latency_ms=0.0,
                decision="d",
            )


# ---------------------------------------------------------------------------
# 9. No I/O, no LLM, no wall clock (deterministic structure)
# ---------------------------------------------------------------------------


class TestNoIOWallclock:
    def test_start_end_time_use_iso_format(self) -> None:
        """Times are ISO strings, not datetime objects — safe for serialization."""
        trace = _make_trace()
        sid = trace.start_span("s")
        span = _get(trace, sid)
        # parseable as ISO
        dt.fromisoformat(span.start_time)
        trace.end_span(sid)
        assert span.end_time is not None
        dt.fromisoformat(span.end_time)

    def test_timeline_serializable(self) -> None:
        """Full trace dumps to JSON-safe dicts without errors."""
        trace = _make_trace("json-test")
        s1 = trace.start_span("a")
        trace.add_event(s1, "evt", v=1)
        trace.llm_call_record(s1, "gpt-4o", "v1", 10, 5, 100.0, "ok")
        trace.end_span(s1)

        timeline = trace.to_timeline()
        # must not raise
        json.dumps(timeline)

    def test_attributes_are_plain_dicts(self) -> None:
        """Attributes hold plain data, no model objects leaked."""
        trace = _make_trace()
        sid = trace.start_span("s", x=42, y="hello")
        span = _get(trace, sid)
        assert isinstance(span.attributes["x"], int)
        assert isinstance(span.attributes["y"], str)

    def test_events_are_plain_dicts(self) -> None:
        """Events are plain dicts, not Pydantic models."""
        trace = _make_trace()
        sid = trace.start_span("s")
        trace.add_event(sid, "evt", key="val")
        span = _get(trace, sid)
        assert isinstance(span.events[0], dict)
        assert not hasattr(span.events[0], "model_dump")
