"""Tests for Alert Rate Limiting - TDD Red phase."""
import pytest

class TestAlertRateLimiting:
    """Alert rate limiting rules per PRD Rule 4."""

    def setup_method(self):
        """Reset rate limiter state before each test."""
        from src.services.rate_limiter import reset_rate_limiter
        reset_rate_limiter()

    def test_max_3_alerts_per_day_per_tenant(self):
        """Max 3 alerts per tenant per day enforced."""
        from src.services.rate_limiter import can_send_alert
        tenant = "test-001"
        # First 3 should pass
        assert can_send_alert(tenant, "alert_1") == True
        assert can_send_alert(tenant, "alert_2") == True
        assert can_send_alert(tenant, "alert_3") == True
        # 4th should fail
        assert can_send_alert(tenant, "alert_4") == False

    def test_same_blindspot_blocked_48h(self):
        """Same blindspot_id blocked within 48h."""
        from src.services.rate_limiter import can_send_alert
        tenant = "test-001"
        blindspot = "runway_critical"
        # First send
        assert can_send_alert(tenant, "runway_1", blindspot_id=blindspot) == True
        # Same blindspot within 48h - should be blocked
        assert can_send_alert(tenant, "runway_2", blindspot_id=blindspot) == False

    def test_info_alerts_accumulate_weekly(self):
        """Info severity alerts accumulate into weekly digest."""
        from src.services.rate_limiter import is_info_alert
        # Info alerts should be marked for accumulation
        assert is_info_alert("severity_info") == True
        assert is_info_alert("severity_warning") == False
        assert is_info_alert("severity_critical") == False

    def test_different_blindspots_allowed(self):
        """Different blindspot_ids allowed even within 48h."""
        from src.services.rate_limiter import can_send_alert
        tenant = "test-001"
        # Same tenant, different blindspots
        assert can_send_alert(tenant, "a1", blindspot_id="runway") == True
        assert can_send_alert(tenant, "a2", blindspot_id="churn") == True
        assert can_send_alert(tenant, "a3", blindspot_id="burn") == True