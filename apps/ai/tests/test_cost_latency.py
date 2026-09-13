"""Tests for cost and latency measurement module.

All tests are pure in-memory — no I/O, no LLM, no wall clock dependencies.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.mission.cost_latency import (
    CostLatencyTracker,
    LLMMetrics,
    MissionMetrics,
    OperationMetrics,
)


# ---------------------------------------------------------------------------
# 1. LLM cost is computed correctly from token counts
# ---------------------------------------------------------------------------


class TestLLMCostComputation:
    """Verify cost = (input_tokens/1000 * input_price) + (output_tokens/1000 * output_price)."""

    def test_gpt4o_cost(self) -> None:
        tracker = CostLatencyTracker()
        llm = tracker.record_llm_call(
            mission_id="m1",
            operation="investigate",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=100.0,
        )
        # gpt-4o: input=$0.0025/1K, output=$0.01/1K
        # input cost = 1000/1000 * 0.0025 = 0.0025
        # output cost = 500/1000 * 0.01 = 0.005
        expected = 0.0025 + 0.005
        assert llm.cost_usd == pytest.approx(expected)

    def test_gpt4o_mini_cost(self) -> None:
        tracker = CostLatencyTracker()
        llm = tracker.record_llm_call(
            mission_id="m1",
            operation="investigate",
            model="gpt-4o-mini",
            input_tokens=2000,
            output_tokens=1000,
            latency_ms=50.0,
        )
        # gpt-4o-mini: input=$0.00015/1K, output=$0.0006/1K
        # input cost = 2000/1000 * 0.00015 = 0.0003
        # output cost = 1000/1000 * 0.0006 = 0.0006
        expected = 0.0003 + 0.0006
        assert llm.cost_usd == pytest.approx(expected)

    def test_claude3_haiku_cost(self) -> None:
        tracker = CostLatencyTracker()
        llm = tracker.record_llm_call(
            mission_id="m1",
            operation="investigate",
            model="claude-3-haiku",
            input_tokens=3000,
            output_tokens=2000,
            latency_ms=80.0,
        )
        # claude-3-haiku: input=$0.00025/1K, output=$0.00125/1K
        # input cost = 3000/1000 * 0.00025 = 0.00075
        # output cost = 2000/1000 * 0.00125 = 0.0025
        expected = 0.00075 + 0.0025
        assert llm.cost_usd == pytest.approx(expected)

    def test_zero_tokens_cost_zero(self) -> None:
        tracker = CostLatencyTracker()
        llm = tracker.record_llm_call(
            mission_id="m1",
            operation="investigate",
            model="gpt-4o",
            input_tokens=0,
            output_tokens=0,
            latency_ms=10.0,
        )
        assert llm.cost_usd == pytest.approx(0.0)

    def test_cost_stored_on_llm_metrics(self) -> None:
        tracker = CostLatencyTracker()
        llm = tracker.record_llm_call(
            mission_id="m1",
            operation="op",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=1000,
            latency_ms=200.0,
        )
        # gpt-4o: 1000/1000*0.0025 + 1000/1000*0.01 = 0.0025 + 0.01 = 0.0125
        assert llm.cost_usd == pytest.approx(0.0125)
        assert llm.model == "gpt-4o"
        assert llm.input_tokens == 1000
        assert llm.output_tokens == 1000
        assert llm.latency_ms == 200.0


# ---------------------------------------------------------------------------
# 2. Unknown models default to GPT-4o pricing
# ---------------------------------------------------------------------------


class TestUnknownModelFallback:
    """Unknown model names fall back to GPT-4o pricing."""

    def test_unknown_model_uses_gpt4o_pricing(self) -> None:
        tracker = CostLatencyTracker()
        llm = tracker.record_llm_call(
            mission_id="m1",
            operation="investigate",
            model="some-unknown-model",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=100.0,
        )
        # Same cost as gpt-4o
        expected = 0.0025 + 0.005
        assert llm.cost_usd == pytest.approx(expected)

    def test_custom_model_same_as_gpt4o(self) -> None:
        tracker = CostLatencyTracker()
        llm_unknown = tracker.record_llm_call(
            mission_id="m1",
            operation="op",
            model="custom-model-v2",
            input_tokens=2000,
            output_tokens=1000,
            latency_ms=50.0,
        )
        tracker2 = CostLatencyTracker()
        llm_known = tracker2.record_llm_call(
            mission_id="m1",
            operation="op",
            model="gpt-4o",
            input_tokens=2000,
            output_tokens=1000,
            latency_ms=50.0,
        )
        assert llm_unknown.cost_usd == pytest.approx(llm_known.cost_usd)


# ---------------------------------------------------------------------------
# 3. Operation metrics aggregate correctly
# ---------------------------------------------------------------------------


class TestOperationAggregation:
    """Operation metrics sum across LLM calls and tool calls."""

    def test_operation_sums_llm_costs(self) -> None:
        tracker = CostLatencyTracker()
        tracker.record_llm_call(
            mission_id="m1",
            operation="investigate",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=100.0,
        )
        tracker.record_llm_call(
            mission_id="m1",
            operation="investigate",
            model="gpt-4o",
            input_tokens=2000,
            output_tokens=1000,
            latency_ms=200.0,
        )
        mission = tracker.get_mission_metrics("m1")
        assert mission is not None
        op = mission.operations[0]
        assert op.operation == "investigate"
        assert len(op.llm_calls) == 2
        assert op.latency_ms == pytest.approx(300.0)
        # cost: (1000/1000*0.0025 + 500/1000*0.01) + (2000/1000*0.0025 + 1000/1000*0.01)
        #     = (0.0025 + 0.005) + (0.005 + 0.01) = 0.0075 + 0.015 = 0.0225
        assert op.total_cost_usd == pytest.approx(0.0225)

    def test_operation_sums_tool_calls(self) -> None:
        tracker = CostLatencyTracker()
        tracker.record_operation(
            mission_id="m1", operation="verify", latency_ms=50.0, tool_calls=3
        )
        tracker.record_operation(
            mission_id="m1", operation="verify", latency_ms=30.0, tool_calls=2
        )
        mission = tracker.get_mission_metrics("m1")
        assert mission is not None
        op = mission.operations[0]
        assert op.tool_calls == 5
        assert op.latency_ms == pytest.approx(80.0)

    def test_mixed_llm_and_tool_calls(self) -> None:
        tracker = CostLatencyTracker()
        tracker.record_llm_call(
            mission_id="m1",
            operation="investigate",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=100.0,
        )
        tracker.record_operation(
            mission_id="m1", operation="investigate", latency_ms=50.0, tool_calls=2
        )
        mission = tracker.get_mission_metrics("m1")
        assert mission is not None
        op = mission.operations[0]
        assert len(op.llm_calls) == 1
        assert op.tool_calls == 2
        assert op.latency_ms == pytest.approx(150.0)

    def test_multiple_operations_on_same_mission(self) -> None:
        tracker = CostLatencyTracker()
        tracker.record_llm_call(
            mission_id="m1",
            operation="investigate",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=100.0,
        )
        tracker.record_llm_call(
            mission_id="m1",
            operation="verify",
            model="gpt-4o",
            input_tokens=500,
            output_tokens=200,
            latency_ms=80.0,
        )
        mission = tracker.get_mission_metrics("m1")
        assert mission is not None
        assert len(mission.operations) == 2
        assert mission.operations[0].operation == "investigate"
        assert mission.operations[1].operation == "verify"


# ---------------------------------------------------------------------------
# 4. Mission metrics sum across operations
# ---------------------------------------------------------------------------


class TestMissionAggregation:
    """Mission metrics aggregate totals from all operations."""

    def test_mission_totals_from_single_operation(self) -> None:
        tracker = CostLatencyTracker()
        tracker.record_llm_call(
            mission_id="m1",
            operation="investigate",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=100.0,
        )
        mission = tracker.get_mission_metrics("m1")
        assert mission is not None
        assert mission.mission_id == "m1"
        assert mission.total_llm_calls == 1
        assert mission.total_tokens == 1500
        assert mission.total_latency_ms == pytest.approx(100.0)
        expected_cost = 0.0025 + 0.005
        assert mission.total_cost_usd == pytest.approx(expected_cost)

    def test_mission_totals_across_operations(self) -> None:
        tracker = CostLatencyTracker()
        # operation 1: investigate
        tracker.record_llm_call(
            mission_id="m1",
            operation="investigate",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=100.0,
        )
        tracker.record_operation(
            mission_id="m1", operation="investigate", latency_ms=50.0, tool_calls=2
        )
        # operation 2: verify
        tracker.record_llm_call(
            mission_id="m1",
            operation="verify",
            model="gpt-4o",
            input_tokens=2000,
            output_tokens=1000,
            latency_ms=200.0,
        )
        mission = tracker.get_mission_metrics("m1")
        assert mission is not None
        assert mission.total_llm_calls == 2
        assert mission.total_tokens == 4500
        assert mission.total_latency_ms == pytest.approx(350.0)

    def test_mission_costs_sum_across_operations(self) -> None:
        tracker = CostLatencyTracker()
        tracker.record_llm_call(
            mission_id="m1",
            operation="a",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=100.0,
        )
        tracker.record_llm_call(
            mission_id="m1",
            operation="b",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=100.0,
        )
        mission = tracker.get_mission_metrics("m1")
        assert mission is not None
        # Two identical calls: each costs 0.0075, total = 0.015
        assert mission.total_cost_usd == pytest.approx(0.015)

    def test_get_unknown_mission_returns_none(self) -> None:
        tracker = CostLatencyTracker()
        assert tracker.get_mission_metrics("nonexistent") is None


# ---------------------------------------------------------------------------
# 5. Resolution ratio computes correctly
# ---------------------------------------------------------------------------


class TestResolutionRatio:
    """Resolution ratio = tool_calls / llm_calls (lower is better)."""

    def test_ratio_with_llm_and_tool_calls(self) -> None:
        tracker = CostLatencyTracker()
        tracker.record_llm_call(
            mission_id="m1",
            operation="investigate",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=100.0,
        )
        tracker.record_operation(
            mission_id="m1", operation="investigate", latency_ms=50.0, tool_calls=4
        )
        ratio = tracker.compute_resolution_ratio("m1")
        assert ratio["llm_calls"] == 1
        assert ratio["tool_calls"] == 4
        assert ratio["ratio"] == pytest.approx(4.0)

    def test_ratio_with_multiple_llm_calls(self) -> None:
        tracker = CostLatencyTracker()
        for _ in range(3):
            tracker.record_llm_call(
                mission_id="m1",
                operation="op",
                model="gpt-4o",
                input_tokens=1000,
                output_tokens=500,
                latency_ms=100.0,
            )
        tracker.record_operation(
            mission_id="m1", operation="op", latency_ms=50.0, tool_calls=6
        )
        ratio = tracker.compute_resolution_ratio("m1")
        assert ratio["llm_calls"] == 3
        assert ratio["tool_calls"] == 6
        assert ratio["ratio"] == pytest.approx(2.0)

    def test_ratio_zero_llm_calls(self) -> None:
        tracker = CostLatencyTracker()
        tracker.record_operation(
            mission_id="m1", operation="op", latency_ms=50.0, tool_calls=5
        )
        ratio = tracker.compute_resolution_ratio("m1")
        assert ratio["llm_calls"] == 0
        assert ratio["tool_calls"] == 5
        assert ratio["ratio"] == 0.0

    def test_ratio_unknown_mission(self) -> None:
        tracker = CostLatencyTracker()
        ratio = tracker.compute_resolution_ratio("nonexistent")
        assert ratio["llm_calls"] == 0
        assert ratio["tool_calls"] == 0
        assert ratio["ratio"] == 0.0

    def test_ratio_no_tool_calls(self) -> None:
        tracker = CostLatencyTracker()
        tracker.record_llm_call(
            mission_id="m1",
            operation="op",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=100.0,
        )
        ratio = tracker.compute_resolution_ratio("m1")
        assert ratio["llm_calls"] == 1
        assert ratio["tool_calls"] == 0
        assert ratio["ratio"] == 0.0


# ---------------------------------------------------------------------------
# 6. Multiple missions tracked independently
# ---------------------------------------------------------------------------


class TestMultiMissionIndependence:
    """Each mission maintains separate state."""

    def test_two_missions_isolated(self) -> None:
        tracker = CostLatencyTracker()
        tracker.record_llm_call(
            mission_id="m1",
            operation="op",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=100.0,
        )
        tracker.record_llm_call(
            mission_id="m2",
            operation="op",
            model="gpt-4o-mini",
            input_tokens=2000,
            output_tokens=1000,
            latency_ms=50.0,
        )
        m1 = tracker.get_mission_metrics("m1")
        m2 = tracker.get_mission_metrics("m2")
        assert m1 is not None
        assert m2 is not None
        assert m1.total_llm_calls == 1
        assert m2.total_llm_calls == 1
        assert m1.total_cost_usd != m2.total_cost_usd

    def test_three_missions_independent_costs(self) -> None:
        tracker = CostLatencyTracker()
        tracker.record_llm_call(
            mission_id="m1",
            operation="a",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=1000,
            latency_ms=100.0,
        )
        tracker.record_llm_call(
            mission_id="m2",
            operation="b",
            model="gpt-4o-mini",
            input_tokens=1000,
            output_tokens=1000,
            latency_ms=100.0,
        )
        tracker.record_llm_call(
            mission_id="m3",
            operation="c",
            model="claude-3-haiku",
            input_tokens=1000,
            output_tokens=1000,
            latency_ms=100.0,
        )
        m1 = tracker.get_mission_metrics("m1")
        m2 = tracker.get_mission_metrics("m2")
        m3 = tracker.get_mission_metrics("m3")
        assert m1 is not None and m2 is not None and m3 is not None
        # All three costs should be different
        costs = {m1.total_cost_usd, m2.total_cost_usd, m3.total_cost_usd}
        assert len(costs) == 3

    def test_resolution_ratio_per_mission(self) -> None:
        tracker = CostLatencyTracker()
        tracker.record_llm_call(
            mission_id="m1",
            operation="op",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=100.0,
        )
        tracker.record_operation(
            mission_id="m1", operation="op", latency_ms=50.0, tool_calls=2
        )
        tracker.record_llm_call(
            mission_id="m2",
            operation="op",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=100.0,
        )
        tracker.record_operation(
            mission_id="m2", operation="op", latency_ms=50.0, tool_calls=10
        )
        r1 = tracker.compute_resolution_ratio("m1")
        r2 = tracker.compute_resolution_ratio("m2")
        assert r1["ratio"] == pytest.approx(2.0)
        assert r2["ratio"] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# 7. All models strict (extra=forbid)
# ---------------------------------------------------------------------------


class TestModelStrictness:
    """Pydantic models reject extra fields and enforce strict types."""

    def test_llm_metrics_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            LLMMetrics(
                model="gpt-4o",
                input_tokens=100,
                output_tokens=50,
                latency_ms=100.0,
                cost_usd=0.01,
                bogus_field="nope",  # type: ignore[arg-type]
            )

    def test_operation_metrics_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            OperationMetrics(
                operation="op",
                latency_ms=100.0,
                tool_calls=0,
                total_cost_usd=0.0,
                extra_field=42,  # type: ignore[arg-type]
            )

    def test_mission_metrics_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            MissionMetrics(
                mission_id="m1",
                total_latency_ms=100.0,
                total_llm_calls=1,
                total_tokens=500,
                total_cost_usd=0.01,
                bad=True,  # type: ignore[arg-type]
            )

    def test_llm_metrics_strict_types_int(self) -> None:
        """input_tokens must be int, not str."""
        with pytest.raises(ValidationError):
            LLMMetrics(
                model="gpt-4o",
                input_tokens="abc",  # type: ignore[arg-type]
                output_tokens=50,
                latency_ms=100.0,
                cost_usd=0.01,
            )

    def test_llm_metrics_strict_types_float(self) -> None:
        """latency_ms must be float, not str."""
        with pytest.raises(ValidationError):
            LLMMetrics(
                model="gpt-4o",
                input_tokens=100,
                output_tokens=50,
                latency_ms="fast",  # type: ignore[arg-type]
                cost_usd=0.01,
            )

    def test_llm_metrics_rejects_negative_tokens(self) -> None:
        """Token counts must be >= 0."""
        with pytest.raises(ValidationError):
            LLMMetrics(
                model="gpt-4o",
                input_tokens=-1,
                output_tokens=50,
                latency_ms=100.0,
                cost_usd=0.01,
            )

    def test_llm_metrics_rejects_negative_cost(self) -> None:
        """Cost must be >= 0."""
        with pytest.raises(ValidationError):
            LLMMetrics(
                model="gpt-4o",
                input_tokens=100,
                output_tokens=50,
                latency_ms=100.0,
                cost_usd=-0.01,
            )
