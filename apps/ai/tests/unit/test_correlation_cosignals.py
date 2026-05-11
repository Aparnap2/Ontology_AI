"""Tests for Correlation Agent CO_SIGNALS - TDD Red phase."""
import pytest
from datetime import datetime, timezone

class TestCorrelationCosignals:
    """CO_SIGNALS cross-signal detection."""

    def test_burn_spike_plus_churn_detected(self):
        """burn_spike + churn detected together should fire."""
        from src.agents.cofounder.correlation import CO_SIGNALS, detect_cosignals
        mission = {
            "burn_alert": True,
            "churn_risk": True,
            "runway_days": 90,
        }
        result = detect_cosignals(mission)
        assert "burn_spike_plus_churn" in result

    def test_error_spike_plus_churn_risk_detected(self):
        """error_spike + churn_risk detected together should fire."""
        from src.agents.cofounder.correlation import detect_cosignals
        mission = {
            "error_spike": True,
            "churn_risk": True,
        }
        result = detect_cosignals(mission)
        assert "error_spike_plus_churn_risk" in result

    def test_short_runway_fundraising_detected(self):
        """short_runway + fundraising context should fire."""
        from src.agents.cofounder.correlation import detect_cosignals
        mission = {
            "runway_days": 90,
            "founder_focus": "fundraising",
        }
        result = detect_cosignals(mission)
        assert "short_runway_fundraising" in result

    def test_no_cosignals_returns_empty(self):
        """No co-signals should return empty list."""
        from src.agents.cofounder.correlation import detect_cosignals
        mission = {
            "burn_alert": False,
            "churn_risk": False,
            "error_spike": False,
            "runway_days": 300,
        }
        result = detect_cosignals(mission)
        assert len(result) == 0

    def test_rate_limit_one_per_day(self):
        """Should enforce one synthesized message per day maximum."""
        from src.agents.cofounder.correlation import can_send_daily_synthesis
        assert can_send_daily_synthesis("test-001") == True