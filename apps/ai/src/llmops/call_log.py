"""LLM call logging — structured records for every LLM interaction.

Emits JSON-structured log entries via the ``llm.calls`` logger.
These records are consumed by log aggregators (ELK, Loki, etc.)
for cost dashboards and latency alerting.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("llm.calls")


def log_llm_call(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    latency_ms: float,
    cost_usd: float,
    tenant_id: str = "",
    agent_name: str = "",
    operation: str = "",
    success: bool = True,
    error: str = "",
) -> None:
    """Log a structured LLM call record.

    Args:
        model: Model identifier (e.g. 'qwen/qwen3-32b').
        prompt_tokens: Number of tokens in the prompt.
        completion_tokens: Number of tokens in the completion.
        total_tokens: Total tokens consumed.
        latency_ms: Round-trip latency in milliseconds.
        cost_usd: Estimated cost in USD.
        tenant_id: Tenant identifier for multi-tenant tracking.
        agent_name: Name of the agent making the call.
        operation: Operation name (e.g. 'decide_alert', 'generate_narrative').
        success: Whether the call succeeded.
        error: Error message if the call failed.
    """
    record: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "latency_ms": round(latency_ms, 1),
        "cost_usd": round(cost_usd, 6),
        "tenant_id": tenant_id,
        "agent_name": agent_name,
        "operation": operation,
        "success": success,
    }
    if error:
        record["error"] = error
    logger.info("LLM call: %s", json.dumps(record))
