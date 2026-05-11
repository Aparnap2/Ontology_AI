"""Tests for Pre-Run Eval Score - TDD Red phase."""
import pytest
from datetime import datetime, timezone, timedelta


class TestPreRunEval:
    """Pre-run eval score gate."""

    def test_low_context_quality_fails_when_similar_events_exist(self):
        """Context quality < 0.65 AND similar events > 0 = fail."""
        from src.llmops.pre_run_eval import evaluate_pre_run
        state = {
            "tenant_id": "test-001",
            "context_quality": 0.3,
            "similar_events_count": 3,
            "graphiti_hit": True,
            "mission_state_updated_at": datetime.now(timezone.utc) - timedelta(seconds=1800),
        }
        result = evaluate_pre_run(state)
        assert result.eval_passed == False
        assert "context_quality" in result.reason.lower()

    def test_low_context_quality_passes_when_no_similar_events(self):
        """Context quality < 0.65 BUT similar events == 0 = pass."""
        from src.llmops.pre_run_eval import evaluate_pre_run
        state = {
            "tenant_id": "test-001",
            "context_quality": 0.3,
            "similar_events_count": 0,
            "graphiti_hit": False,
            "mission_state_updated_at": datetime.now(timezone.utc) - timedelta(seconds=1800),
        }
        result = evaluate_pre_run(state)
        assert result.eval_passed == True
        assert result.reason == "all gates passed"

    def test_high_context_quality_passes_regardless_of_similar_events(self):
        """Context quality > 0.65 = pass regardless of similar events."""
        from src.llmops.pre_run_eval import evaluate_pre_run
        state = {
            "tenant_id": "test-001",
            "context_quality": 0.8,
            "similar_events_count": 5,
            "graphiti_hit": True,
            "mission_state_updated_at": datetime.now(timezone.utc) - timedelta(seconds=1800),
        }
        result = evaluate_pre_run(state)
        assert result.eval_passed == True
        assert result.reason == "all gates passed"

    def test_stale_mission_state_fails(self):
        """Mission state older than 1h fails regardless."""
        from src.llmops.pre_run_eval import evaluate_pre_run
        state = {
            "tenant_id": "test-001",
            "context_quality": 0.7,
            "similar_events_count": 0,
            "graphiti_hit": True,
            "mission_state_updated_at": datetime.now(timezone.utc) - timedelta(seconds=4000),
        }
        result = evaluate_pre_run(state)
        assert result.eval_passed == False
        assert "stale" in result.reason.lower() or "3600" in result.reason

    def test_all_gates_pass(self):
        """All gates pass = eval_passed."""
        from src.llmops.pre_run_eval import evaluate_pre_run
        state = {
            "tenant_id": "test-001",
            "context_quality": 0.85,
            "similar_events_count": 1,
            "graphiti_hit": True,
            "mission_state_updated_at": datetime.now(timezone.utc) - timedelta(seconds=300),
        }
        result = evaluate_pre_run(state)
        assert result.eval_passed == True
        assert "all gates passed" in result.reason.lower()