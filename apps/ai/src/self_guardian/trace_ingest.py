"""Trace Ingestion — Langfuse trace to AgentObservation mapper.

Ingests Langfuse trace dicts and converts them into typed
AgentObservation records for the Self-Guardian detector.
Deterministic code only — no LLM calls.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from src.schemas.self_guardian import AgentObservation

log = logging.getLogger(__name__)

_DEFAULT_DEDUP_MINUTES = 60


def map_trace_to_observation(trace: dict[str, Any]) -> AgentObservation | None:
    """Deterministic mapping from Langfuse trace dict to AgentObservation.

    No LLM calls — pure dict field extraction. Returns None if the
    trace dict cannot be parsed (logs a warning).
    """
    if not isinstance(trace, dict) or "id" not in trace:
        log.warning("Cannot map trace: missing 'id' field")
        return None

    trace_id = str(trace.get("id", ""))

    agent_name = str(trace.get("user_id") or "")
    if not agent_name:
        for tag in trace.get("tags") or []:
            tag_str = str(tag)
            if tag_str.startswith("agent:"):
                agent_name = tag_str[len("agent:"):]
                break
    if not agent_name:
        agent_name = "unknown"

    action = str(trace.get("name") or "unknown_action")

    tool_id: str | None = None
    for tag in trace.get("tags") or []:
        tag_str = str(tag)
        if tag_str.startswith("tool:"):
            tool_id = tag_str[len("tool:"):]
            break
    if tool_id is None:
        observations = trace.get("observations") or []
        if observations:
            first = observations[0] if isinstance(observations, list) else observations
            if isinstance(first, dict):
                meta = first.get("metadata") or {}
                tool_id = meta.get("tool_id")

    target_entity = str(trace.get("session_id") or "")
    if not target_entity:
        inp = trace.get("input")
        if inp:
            target_entity = str(inp)[:80]

    try:
        raw_ts = trace.get("start_time")
        if isinstance(raw_ts, str):
            timestamp = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        elif isinstance(raw_ts, datetime):
            timestamp = raw_ts
        else:
            timestamp = datetime.now(timezone.utc)
    except (ValueError, TypeError):
        timestamp = datetime.now(timezone.utc)

    duration_ms = 0
    try:
        start_raw = trace.get("start_time")
        end_raw = trace.get("end_time")
        if start_raw and end_raw:
            if isinstance(start_raw, str):
                start_dt = datetime.fromisoformat(str(start_raw).replace("Z", "+00:00"))
            elif isinstance(start_raw, datetime):
                start_dt = start_raw
            else:
                start_dt = None
            if isinstance(end_raw, str):
                end_dt = datetime.fromisoformat(str(end_raw).replace("Z", "+00:00"))
            elif isinstance(end_raw, datetime):
                end_dt = end_raw
            else:
                end_dt = None
            if start_dt and end_dt:
                duration_ms = int((end_dt - start_dt).total_seconds() * 1000)
    except (ValueError, TypeError):
        pass

    status = trace.get("status")
    if status is None:
        observations = trace.get("observations") or []
        if observations:
            first = observations[0] if isinstance(observations, list) else observations
            if isinstance(first, dict):
                status = first.get("status", "unknown")
        else:
            status = "unknown"

    success = str(status).lower() == "completed"

    error_message: str | None = trace.get("error")
    if not error_message:
        observations = trace.get("observations") or []
        if observations:
            first = observations[0] if isinstance(observations, list) else observations
            if isinstance(first, dict):
                error_message = first.get("error")

    return AgentObservation(
        agent_name=agent_name,
        action=action,
        tool_id=tool_id,
        target_entity=target_entity,
        timestamp=timestamp,
        trace_id=trace_id,
        duration_ms=duration_ms,
        success=success,
        error_message=error_message,
    )


class TraceIngester:
    """Ingests Langfuse traces and converts to AgentObservation records.

    Supports deduplication by trace_id within a configurable time window.
    Thread-safe. Gracefully handles Langfuse unavailability.
    """

    def __init__(
        self,
        collector: Any | None = None,
        dedup_window_minutes: int = _DEFAULT_DEDUP_MINUTES,
    ) -> None:
        self._collector = collector
        self._dedup_window = timedelta(minutes=dedup_window_minutes)
        self._lock = threading.Lock()
        self._seen_trace_ids: dict[str, datetime] = {}
        self._stats: dict[str, int | datetime | None] = {
            "total_ingested": 0,
            "total_deduped": 0,
            "total_failed": 0,
            "last_ingest_time": None,
        }

    def ingest_trace(self, trace_data: dict[str, Any]) -> AgentObservation | None:
        """Ingest a single Langfuse trace dict.

        Returns the AgentObservation if successfully mapped and not
        deduplicated. Returns None if parse fails or already seen.
        """
        if not isinstance(trace_data, dict):
            log.warning("ingest_trace called with non-dict: %s", type(trace_data).__name__)
            with self._lock:
                self._stats["total_failed"] += 1
            return None

        trace_id = trace_data.get("id")
        if not trace_id:
            log.warning("Trace missing 'id' field — skipping")
            with self._lock:
                self._stats["total_failed"] += 1
            return None

        trace_id_str = str(trace_id)

        with self._lock:
            if trace_id_str in self._seen_trace_ids:
                last_seen = self._seen_trace_ids[trace_id_str]
                if datetime.now(timezone.utc) - last_seen < self._dedup_window:
                    self._stats["total_deduped"] += 1
                    log.debug("Deduped trace: %s", trace_id_str)
                    return None

        observation = map_trace_to_observation(trace_data)
        if observation is None:
            with self._lock:
                self._stats["total_failed"] += 1
            return None

        with self._lock:
            self._seen_trace_ids[trace_id_str] = datetime.now(timezone.utc)
            self._stats["total_ingested"] += 1
            self._stats["last_ingest_time"] = datetime.now(timezone.utc)

        if self._collector is not None:
            self._collector.record_observation(observation)

        return observation

    async def ingest_from_langfuse(
        self, trace_ids: list[str]
    ) -> list[AgentObservation]:
        """Fetch traces from Langfuse API by ID and ingest them.

        Gracefully handles Langfuse connection errors.
        Returns list of successfully ingested observations.
        """
        if not trace_ids:
            return []

        try:
            from src.services.langfuse_client import _get_langfuse
            client = _get_langfuse()
            if client is None:
                log.warning("Langfuse client unavailable — skipping trace fetch")
                return []
        except Exception as exc:
            log.warning("Langfuse import failed: %s", exc)
            return []

        results: list[AgentObservation] = []
        for tid in trace_ids:
            try:
                trace_data = client.get_trace(tid)
                if not isinstance(trace_data, dict):
                    trace_data = trace_data.model_dump() if hasattr(trace_data, "model_dump") else {}
                obs = self.ingest_trace(trace_data)
                if obs is not None:
                    results.append(obs)
            except Exception as exc:
                log.warning("Failed to fetch/ingest trace %s: %s", tid, exc)
                with self._lock:
                    self._stats["total_failed"] += 1

        return results

    def get_stats(self) -> dict[str, int | datetime | None]:
        """Return ingestion stats."""
        with self._lock:
            return dict(self._stats)
