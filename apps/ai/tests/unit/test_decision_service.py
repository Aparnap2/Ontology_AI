"""
Unit tests for Decision Service
"""
import pytest
from unittest.mock import patch, MagicMock


class TestDecisionService:
    """Test DecisionService.evaluate() and routing logic."""

    def test_evaluate_returns_decision_result(self):
        """Test that evaluate returns a valid DecisionResult."""
        from apps.ai.src.services.decision import DecisionService, Severity

        service = DecisionService()
        result = service.evaluate("tenant-123", {"monthly_churn_pct": 0.05})

        assert result.tenant_id == "tenant-123"
        assert result.should_alert is True
        assert result.severity in [Severity.CRITICAL, Severity.WARNING, Severity.INFO]
        assert 0.0 <= result.confidence <= 1.0

    def test_evaluate_churn_detection(self):
        """Test FG-01 pattern detection for high churn."""
        from apps.ai.src.services.decision import DecisionService

        service = DecisionService()
        result = service.evaluate("tenant-123", {"monthly_churn_pct": 0.05})

        assert result.should_alert is True
        assert result.pattern_name == "FG-01"

    def test_evaluate_burn_multiple_detection(self):
        """Test FG-02 pattern detection for high burn multiple."""
        from apps.ai.src.services.decision import DecisionService

        service = DecisionService()
        # FG-02 requires net_burn and net_new_arr signals
        result = service.evaluate("tenant-123", {
            "net_burn": 5000,
            "net_new_arr": 2000  # burn_multiple = 2.5
        })

        assert result.should_alert is True
        assert result.pattern_name == "FG-02"

    def test_evaluate_activation_wall_detection(self):
        """Test BG-01 pattern detection for low activation."""
        from apps.ai.src.services.decision import DecisionService

        service = DecisionService()
        # BG-01 requires new_signups, activation_rate, mrr_growth_pct
        result = service.evaluate("tenant-123", {
            "new_signups": 100,
            "activation_rate": 0.15,  # below 0.40 threshold
            "mrr_growth_pct": 0.05
        })

        assert result.should_alert is True
        assert result.pattern_name == "BG-01"

    def test_hitl_required_for_critical_low_confidence(self):
        """Test HITL routing for critical severity with low confidence."""
        from apps.ai.src.services.decision import DecisionService

        service = DecisionService()
        # Send signals that trigger a critical pattern with low confidence
        # Using very high burn to trigger critical severity
        result = service.evaluate("tenant-123", {
            "net_burn": 50000,  # Very high
            "net_new_arr": 10000,  # burn_multiple = 5.0 (very high)
            "confidence": 0.4  # Low confidence override
        })

        # Should have hitl_required True due to critical severity
        assert result.hitl_required is True

    def test_no_alert_for_normal_metrics(self):
        """Test that normal metrics don't trigger alerts."""
        from apps.ai.src.services.decision import DecisionService

        service = DecisionService()
        result = service.evaluate("tenant-123", {
            "monthly_churn_pct": 0.01,
            "burn_multiple": 1.0,
            "activation_rate": 0.5
        })

        assert result.should_alert is False

    def test_insight_generation(self):
        """Test that insight is generated for alerts."""
        from apps.ai.src.services.decision import DecisionService

        service = DecisionService()
        result = service.evaluate("tenant-123", {"monthly_churn_pct": 0.05})

        assert result.insight is not None
        assert len(result.insight) > 0
        assert "churn" in result.insight.lower() or "threshold" in result.insight.lower()

    def test_decision_id_is_unique(self):
        """Test that each decision gets a unique ID."""
        from apps.ai.src.services.decision import DecisionService

        service = DecisionService()
        result1 = service.evaluate("tenant-123", {"monthly_churn_pct": 0.05})
        result2 = service.evaluate("tenant-123", {"monthly_churn_pct": 0.05})

        assert result1.decision_id != result2.decision_id

    @pytest.mark.asyncio
    async def test_publish_result_returns_bool(self):
        """Test that publish_result returns a boolean."""
        from apps.ai.src.services.decision import DecisionService

        service = DecisionService()
        result = service.evaluate("tenant-123", {})

        # Should return bool even if publish fails
        publish_result = await service.publish_result(result)
        assert isinstance(publish_result, bool)


class TestDecisionSchemas:
    """Test Pydantic schemas for decision service."""

    def test_decision_result_validation(self):
        """Test DecisionResult validates required fields."""
        from apps.ai.src.services.decision import DecisionResult, Severity

        result = DecisionResult(
            tenant_id="tenant-123",
            should_alert=True,
            severity=Severity.CRITICAL,
            confidence=0.85
        )

        assert result.tenant_id == "tenant-123"
        assert result.should_alert is True

    def test_confidence_bounds(self):
        """Test confidence must be between 0 and 1."""
        from apps.ai.src.services.decision import DecisionResult, Severity
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            DecisionResult(
                tenant_id="tenant-123",
                should_alert=True,
                severity=Severity.CRITICAL,
                confidence=1.5  # Out of bounds
            )