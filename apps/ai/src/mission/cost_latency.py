"""Cost and Latency Measurement — deterministic tracking for agent operations.

Records every LLM call and tool invocation per mission, computes costs
from token counts and model pricing, and aggregates metrics per operation
and per mission.  Pure in-memory bookkeeping — no I/O, no wall clock.

Resolution Ratio
----------------
The ``compute_resolution_ratio`` method tracks the deterministic-context-to-
LLM ratio.  Goal: ONE useful investigation call, not LLM->tool->LLM->tool
loops.  Returns ``{"llm_calls": N, "tool_calls": M, "ratio": M/N}`` where
lower ratio is better (fewer tool calls per LLM call).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ── Models ───────────────────────────────────────────────────────────────


class LLMMetrics(BaseModel):
    """Metrics for one LLM call."""

    model_config = ConfigDict(extra="forbid", strict=True)

    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)
    cost_usd: float = Field(ge=0.0)


class OperationMetrics(BaseModel):
    """Metrics for one operation (investigation, verification, etc.)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    operation: str
    latency_ms: float = Field(ge=0.0)
    llm_calls: list[LLMMetrics] = Field(default_factory=list)
    tool_calls: int = Field(ge=0, default=0)
    total_cost_usd: float = Field(ge=0.0, default=0.0)


class MissionMetrics(BaseModel):
    """Aggregated metrics for one mission."""

    model_config = ConfigDict(extra="forbid", strict=True)

    mission_id: str
    total_latency_ms: float = Field(ge=0.0)
    total_llm_calls: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    total_cost_usd: float = Field(ge=0.0)
    operations: list[OperationMetrics] = Field(default_factory=list)


# ── Tracker ──────────────────────────────────────────────────────────────


class CostLatencyTracker:
    """Tracks cost and latency for missions.

    Pricing is per-1K tokens.  Unknown models fall back to GPT-4o pricing.
    """

    MODEL_PRICING: dict[str, dict[str, float]] = {
        "gpt-4o": {"input": 0.0025, "output": 0.01},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    }

    _DEFAULT_MODEL = "gpt-4o"

    def __init__(self) -> None:
        self._missions: dict[str, MissionMetrics] = {}

    # ── cost computation ─────────────────────────────────────────────

    def _compute_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Compute cost in USD from token counts and model pricing."""
        pricing = self.MODEL_PRICING.get(model, self.MODEL_PRICING[self._DEFAULT_MODEL])
        input_cost = (input_tokens / 1000.0) * pricing["input"]
        output_cost = (output_tokens / 1000.0) * pricing["output"]
        return round(input_cost + output_cost, 10)

    # ── internal helpers ─────────────────────────────────────────────

    def _ensure_mission(self, mission_id: str) -> MissionMetrics:
        """Return existing mission metrics or create a new one."""
        if mission_id not in self._missions:
            self._missions[mission_id] = MissionMetrics(
                mission_id=mission_id,
                total_latency_ms=0.0,
                total_llm_calls=0,
                total_tokens=0,
                total_cost_usd=0.0,
                operations=[],
            )
        return self._missions[mission_id]

    def _ensure_operation(
        self, mission: MissionMetrics, operation: str
    ) -> OperationMetrics:
        """Return existing operation for a mission or create a new one."""
        for op in mission.operations:
            if op.operation == operation:
                return op
        op = OperationMetrics(
            operation=operation,
            latency_ms=0.0,
            llm_calls=[],
            tool_calls=0,
            total_cost_usd=0.0,
        )
        mission.operations.append(op)
        return op

    # ── public API ───────────────────────────────────────────────────

    def record_llm_call(
        self,
        mission_id: str,
        operation: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
    ) -> LLMMetrics:
        """Record an LLM call and compute cost.

        Creates the mission and operation if they do not exist yet.
        Returns the computed :class:`LLMMetrics`.
        """
        cost = self._compute_cost(model, input_tokens, output_tokens)
        metrics = LLMMetrics(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
        )

        mission = self._ensure_mission(mission_id)
        op = self._ensure_operation(mission, operation)

        op.llm_calls.append(metrics)
        op.latency_ms += latency_ms
        op.total_cost_usd += cost

        mission.total_latency_ms += latency_ms
        mission.total_llm_calls += 1
        mission.total_tokens += input_tokens + output_tokens
        mission.total_cost_usd += cost

        logger.info(
            "llm_call recorded",
            extra={
                "mission_id": mission_id,
                "operation": operation,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency_ms": latency_ms,
                "cost_usd": cost,
            },
        )
        return metrics

    def record_operation(
        self,
        mission_id: str,
        operation: str,
        latency_ms: float,
        tool_calls: int = 0,
    ) -> OperationMetrics:
        """Record a tool-based operation (no LLM call, just tool invocations).

        Creates the mission and operation if they do not exist yet.
        Returns the updated :class:`OperationMetrics`.
        """
        mission = self._ensure_mission(mission_id)
        op = self._ensure_operation(mission, operation)

        op.latency_ms += latency_ms
        op.tool_calls += tool_calls

        mission.total_latency_ms += latency_ms

        logger.info(
            "operation recorded",
            extra={
                "mission_id": mission_id,
                "operation": operation,
                "latency_ms": latency_ms,
                "tool_calls": tool_calls,
            },
        )
        return op

    def get_mission_metrics(self, mission_id: str) -> MissionMetrics | None:
        """Return aggregated metrics for a mission, or None if unknown."""
        return self._missions.get(mission_id)

    def compute_resolution_ratio(self, mission_id: str) -> dict[str, Any]:
        """Compute the deterministic-context-to-LLM ratio.

        Goal: ONE useful investigation call, not LLM->tool->LLM->tool loops.

        Returns ``{"llm_calls": N, "tool_calls": M, "ratio": M/N}`` where
        lower ratio is better (fewer tool calls per LLM call).
        Returns ``{"llm_calls": 0, "tool_calls": 0, "ratio": 0.0}`` when
        there are no LLM calls (avoids division by zero).
        """
        mission = self._missions.get(mission_id)
        if mission is None:
            return {"llm_calls": 0, "tool_calls": 0, "ratio": 0.0}

        total_llm = mission.total_llm_calls
        total_tool = sum(op.tool_calls for op in mission.operations)

        if total_llm == 0:
            return {"llm_calls": 0, "tool_calls": total_tool, "ratio": 0.0}

        ratio = total_tool / total_llm
        return {"llm_calls": total_llm, "tool_calls": total_tool, "ratio": ratio}
