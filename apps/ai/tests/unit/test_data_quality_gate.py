"""Tests for Data Quality Gate - TDD Red phase."""
import pytest
from datetime import datetime, timezone, timedelta


class TestDataQualityGate:
    """Data quality checks before agent runs."""

    def test_freshness_check_fails_old_data(self):
        """Data older than 2h should fail."""
        from src.workflows.nodes.data_quality_gate import run_data_quality_gate
        from src.session.mission_state import MissionState
        state = MissionState(tenant_id="test-001")
        state.data_last_synced = datetime.now(timezone.utc) - timedelta(hours=3)
        result = run_data_quality_gate(state)
        assert result.data_quality.passed == False
        assert "data_stale" in result.data_quality.reason

    def test_numeric_sanity_fails_negative_runway(self):
        """Negative runway_days is data corruption."""
        from src.workflows.nodes.data_quality_gate import run_data_quality_gate
        from src.session.mission_state import MissionState
        state = MissionState(tenant_id="test-001")
        state.runway_days = -5
        result = run_data_quality_gate(state)
        assert result.data_quality.passed == False
        assert "runway_negative" in result.data_quality.reason

    def test_numeric_sanity_fails_churn_over_100pct(self):
        """Churn rate > 100% is impossible."""
        from src.workflows.nodes.data_quality_gate import run_data_quality_gate
        from src.session.mission_state import MissionState
        state = MissionState(tenant_id="test-001")
        state.churn_rate = 1.5
        result = run_data_quality_gate(state)
        assert result.data_quality.passed == False
        assert "churn_rate_over_100pct" in result.data_quality.reason

    def test_numeric_sanity_fails_negative_burn(self):
        """Negative burn_rate is data corruption."""
        from src.workflows.nodes.data_quality_gate import run_data_quality_gate
        from src.session.mission_state import MissionState
        state = MissionState(tenant_id="test-001")
        state.burn_rate = -1000
        result = run_data_quality_gate(state)
        assert result.data_quality.passed == False
        assert "burn_negative" in result.data_quality.reason

    def test_required_fields_fails_missing_mrr(self):
        """MRR is required for finance agent."""
        from src.workflows.nodes.data_quality_gate import run_data_quality_gate
        from src.session.mission_state import MissionState
        state = MissionState(tenant_id="test-001")
        state.mrr = None
        result = run_data_quality_gate(state)
        assert result.data_quality.passed == False
        assert "mrr_missing" in result.data_quality.reason

    def test_passes_with_valid_data(self):
        """Valid data should pass all checks."""
        from src.workflows.nodes.data_quality_gate import run_data_quality_gate
        from src.session.mission_state import MissionState
        state = MissionState(tenant_id="test-001")
        state.mrr = 10000
        state.runway_days = 120
        state.burn_rate = 5000
        state.churn_rate = 0.02
        state.data_last_synced = datetime.now(timezone.utc) - timedelta(minutes=30)
        result = run_data_quality_gate(state)
        assert result.data_quality.passed == True