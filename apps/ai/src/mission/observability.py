"""Structured execution trace for mission observability.

Records every step of a mission execution as typed spans with
parent-child relationships, events, and LLM call metadata.

No I/O, no LLM, no wall clock — pure in-memory bookkeeping.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class TraceSpan(BaseModel):
    """One step in the execution trace."""

    model_config = {"extra": "forbid", "strict": True}

    span_id: str
    parent_span_id: str | None
    trace_id: str
    name: str
    start_time: str
    end_time: str | None = None
    status: str = "ok"
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)


class LLMCallRecord(BaseModel):
    """LLM call metadata attached to a span."""

    model_config = {"extra": "forbid", "strict": True}

    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    decision: str


class ExecutionTrace:
    """Collects spans for one mission execution.

    Designed for single-threaded callers (Temporal activities). Not thread-safe.
    """

    def __init__(self, trace_id: str) -> None:
        self.trace_id = trace_id
        self.spans: list[TraceSpan] = []
        self._index: dict[str, TraceSpan] = {}

    def start_span(self, name: str, parent: str | None = None, **attrs: Any) -> str:
        """Start a new span, return span_id."""
        span_id = uuid.uuid4().hex[:16]
        now = datetime.now(timezone.utc).isoformat()
        span = TraceSpan(
            span_id=span_id,
            parent_span_id=parent,
            trace_id=self.trace_id,
            name=name,
            start_time=now,
            status="ok",
            attributes=dict(attrs),
        )
        self.spans.append(span)
        self._index[span_id] = span
        return span_id

    def end_span(self, span_id: str, status: str = "ok") -> None:
        """End a span."""
        span = self._index.get(span_id)
        if span is None:
            raise KeyError(f"span not found: {span_id}")
        span.end_time = datetime.now(timezone.utc).isoformat()
        span.status = status

    def add_event(self, span_id: str, name: str, **attrs: Any) -> None:
        """Add an event to a span."""
        span = self._index.get(span_id)
        if span is None:
            raise KeyError(f"span not found: {span_id}")
        now = datetime.now(timezone.utc).isoformat()
        span.events.append({"name": name, "timestamp": now, **attrs})

    def get_span(self, span_id: str) -> TraceSpan | None:
        """Get a span by ID."""
        return self._index.get(span_id)

    def to_timeline(self) -> list[dict[str, Any]]:
        """Export trace as a timeline (sorted by start_time)."""
        sorted_spans = sorted(self.spans, key=lambda s: s.start_time)
        return [s.model_dump() for s in sorted_spans]

    def llm_call_record(
        self,
        span_id: str,
        model: str,
        prompt_version: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
        decision: str,
    ) -> None:
        """Record LLM call details on a span."""
        span = self._index.get(span_id)
        if span is None:
            raise KeyError(f"span not found: {span_id}")
        record = LLMCallRecord(
            model=model,
            prompt_version=prompt_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            decision=decision,
        )
        span.attributes["llm_call"] = record.model_dump()
