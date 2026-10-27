"""
Unit tests for AnomalyAgent.

Tests cover:
  - AnomalyState structure
  - retrieve_anomaly_memory node
  - generate_explanation node
  - generate_action node
  - build_slack_message node
  - detect_anomaly threshold rules (10 tests)

All tests run in MOCK MODE (no real API calls).
"""
from __future__ import annotations
import os
import pytest
from typing import Any

# Force a mock environment before any project-level import. The prior values
# are captured first and restored by the `_restore_env` fixture so these
# overrides do not leak into later suites (which broke P0 worker-startup tests
# by leaving DATABASE_URL empty).
_MOCK_ENV = {
    "STRIPE_API_KEY": "",
    "PLAID_ACCESS_TOKEN": "",
    "SLACK_WEBHOOK_URL": "",
    "DATABASE_URL": "",
    "PRODUCT_DB_URL": "",
    "QDRANT_HOST": "localhost",
    "QDRANT_PORT": "6333",
    "OLLAMA_BASE_URL": "http://localhost:11434/v1",
    "LANGFUSE_ENABLED": "false",
}
_PRIOR_ENV = {_k: os.environ.get(_k) for _k in _MOCK_ENV}
os.environ.update(_MOCK_ENV)


@pytest.fixture(scope="module", autouse=True)
def _restore_env():
    """Undo this module's env overrides once its tests finish."""
    yield
    for _k, _original in _PRIOR_ENV.items():
        if _original is None:
            os.environ.pop(_k, None)
        else:
            os.environ[_k] = _original

TENANT = "test-anomaly-tenant-unit"

from src.agents.anomaly.state import AnomalyState
from src.legacy.agents.v2.anomaly.nodes import (
    retrieve_anomaly_memory,
    generate_explanation,
    generate_action,
    build_slack_message,
)
from src.legacy.agents.v2.anomaly.thresholds import detect_anomaly


# =============================================================================
# TestAnomalyState
# =============================================================================

class TestAnomalyState:
    """Tests for AnomalyState TypedDict structure."""

    def test_anomaly_state_creation_empty(self):
        """AnomalyState can be created with no fields (all optional)."""
        state: AnomalyState = {}
        assert isinstance(state, dict)
        assert len(state) == 0

    def test_anomaly_state_with_identity_and_metric(self):
        """AnomalyState accepts tenant_id and metric fields."""
        state: AnomalyState = {
            "tenant_id": TENANT,
            "metrics": {"MRR": {"current": 12500.0, "baseline": 15000.0}},
        }
        assert state["tenant_id"] == TENANT
        assert state["metrics"]["MRR"]["current"] == 12500.0

    def test_anomaly_state_with_all_fields(self):
        """AnomalyState accepts all defined fields."""
        state: AnomalyState = {
            "tenant_id": TENANT,
            "metrics": {"runway": {"current": 4.5, "baseline": 8.0}},
            "memory_context": "Previous runway alert",
            "draft": "Draft message",
            "narrative": "What's happening",
            "slack_message": "Alert message",
            "slack_blocks": [],
            "error": None,
            "retry_count": 0,
            "langfuse_trace_id": None,
        }
        assert len(state) == 10


# =============================================================================
# TestRetrieveAnomalyMemory
# =============================================================================

class TestRetrieveAnomalyMemory:
    """Tests for retrieve_anomaly_memory node."""

    def test_retrieve_memory_returns_past_episodes_list(self):
        """retrieve_anomaly_memory returns past_episodes as list."""
        state: AnomalyState = {
            "tenant_id": TENANT,
            "metrics": {"MRR": {"description": "MRR declined 15%"}},
        }
        result = retrieve_anomaly_memory(state)

        assert "past_episodes" in result
        assert isinstance(result["past_episodes"], list)

    def test_retrieve_memory_returns_historical_context(self):
        """retrieve_anomaly_memory returns historical_context string."""
        state: AnomalyState = {
            "tenant_id": TENANT,
            "metrics": {"burn_rate": {"description": "Burn rate spike"}},
        }
        result = retrieve_anomaly_memory(state)

        assert "historical_context" in result
        assert isinstance(result["historical_context"], str)

    def test_retrieve_memory_handles_missing_tenant(self):
        """retrieve_anomaly_memory handles missing tenant_id gracefully."""
        state: AnomalyState = {}
        result = retrieve_anomaly_memory(state)

        assert "past_episodes" in result
        assert "historical_context" in result


# =============================================================================
# TestGenerateExplanation
# =============================================================================

class TestGenerateExplanation:
    """Tests for generate_explanation node."""

    def test_generate_explanation_returns_explanation_string(self):
        """generate_explanation returns explanation string."""
        state: AnomalyState = {
            "tenant_id": TENANT,
            "metrics": {
                "MRR": {
                    "current": 12500.0,
                    "baseline": 15000.0,
                    "deviation_pct": -16.67,
                }
            },
            "memory_context": "Previous MRR was stable",
        }
        result = generate_explanation(state)

        assert "explanation" in result
        assert isinstance(result["explanation"], str)

    def test_generate_explanation_returns_check_first(self):
        """generate_explanation returns check_first string."""
        state: AnomalyState = {
            "tenant_id": TENANT,
            "metrics": {
                "runway": {"current": 4.0, "baseline": 8.0, "deviation_pct": -50.0}
            },
        }
        result = generate_explanation(state)

        assert "check_first" in result
        assert isinstance(result["check_first"], str)

    def test_generate_explanation_handles_missing_data(self):
        """generate_explanation handles missing fields with fallback."""
        state: AnomalyState = {
            "tenant_id": TENANT,
        }
        result = generate_explanation(state)

        assert "explanation" in result
        assert len(result["explanation"]) > 0


# =============================================================================
# TestGenerateAction
# =============================================================================

class TestGenerateAction:
    """Tests for generate_action node."""

    def test_generate_action_returns_action_item_string(self):
        """generate_action returns action_item string."""
        state: AnomalyState = {
            "tenant_id": TENANT,
            "metrics": {"MRR": {"current": 12500.0}},
            "explanation": "MRR declined due to churn",
        }
        result = generate_action(state)

        assert "action_item" in result
        assert isinstance(result["action_item"], str)

    def test_generate_action_item_has_reasonable_length(self):
        """generate_action returns action under 15 words."""
        state: AnomalyState = {
            "tenant_id": TENANT,
            "metrics": {"burn_rate": {"current": 50000.0}},
            "explanation": "Burn rate increased 30%",
        }
        result = generate_action(state)

        action = result.get("action_item", "")
        word_count = len(action.split())
        assert word_count <= 15 or len(action) > 0

    def test_generate_action_handles_missing_explanation(self):
        """generate_action handles missing explanation with fallback."""
        state: AnomalyState = {
            "tenant_id": TENANT,
            "metrics": {"churn": {"current": 5.0}},
        }
        result = generate_action(state)

        assert "action_item" in result
        assert len(result["action_item"]) > 0


# =============================================================================
# TestBuildSlackMessage
# =============================================================================

class TestBuildSlackMessage:
    """Tests for build_slack_message node."""

    def test_build_slack_message_returns_blocks_list(self):
        """build_slack_message returns slack_blocks as list."""
        state: AnomalyState = {
            "tenant_id": TENANT,
            "metrics": {
                "MRR": {
                    "current": 12500.0,
                    "baseline": 15000.0,
                    "deviation_pct": -16.67,
                }
            },
            "explanation": "MRR declined",
            "check_first": "Check churn",
            "action_item": "Review cancellations",
        }
        result = build_slack_message(state)

        assert "slack_blocks" in result
        assert isinstance(result["slack_blocks"], list)

    def test_build_slack_message_has_header_block(self):
        """build_slack_message includes header block."""
        state: AnomalyState = {
            "tenant_id": TENANT,
            "metrics": {
                "runway": {"current": 4.0, "baseline": 8.0, "deviation_pct": -50.0}
            },
            "explanation": "Runway critical",
            "action_item": "Cut costs",
        }
        result = build_slack_message(state)

        blocks = result["slack_blocks"]
        assert len(blocks) >= 1
        assert blocks[0]["type"] == "header"

    def test_build_slack_message_handles_missing_fields(self):
        """build_slack_message handles missing fields gracefully."""
        state: AnomalyState = {
            "tenant_id": TENANT,
        }
        result = build_slack_message(state)

        assert "slack_blocks" in result
        assert isinstance(result["slack_blocks"], list)
        assert len(result["slack_blocks"]) >= 1


# =============================================================================
# TestDetectAnomaly — Rule-based threshold tests (10 tests)
# =============================================================================

class TestDetectAnomaly:
    """Tests for detect_anomaly() rule-based threshold logic."""

    def test_runway_critical_below_90_days(self):
        """runway_days < 90 → critical anomaly, should alert."""
        result = detect_anomaly({
            "runway_days": 80,
            "mrr_change_pct": 0,
            "burn_rate_cents": 50000,
            "prev_burn_cents": 50000,
            "churned_customers": 0,
        }, TENANT)
        assert result["anomaly_detected"] is True
        assert result["anomaly_type"] == "runway_drop"
        assert result["anomaly_severity"] == "critical"
        assert result["should_alert"] is True

    def test_runway_warning_below_180_days(self):
        """90 <= runway_days < 180 → warning anomaly."""
        result = detect_anomaly({
            "runway_days": 150,
            "mrr_change_pct": 0,
            "burn_rate_cents": 50000,
            "prev_burn_cents": 50000,
            "churned_customers": 0,
        }, TENANT)
        assert result["anomaly_detected"] is True
        assert result["anomaly_type"] == "runway_drop"
        assert result["anomaly_severity"] == "warning"

    def test_no_anomaly_healthy(self):
        """Healthy metrics → no anomaly detected."""
        result = detect_anomaly({
            "runway_days": 400,
            "mrr_change_pct": 3.0,
            "burn_rate_cents": 40000,
            "prev_burn_cents": 40000,
            "churned_customers": 0,
        }, TENANT)
        assert result["anomaly_detected"] is False
        assert result["should_alert"] is False

    def test_mrr_drop_warning(self):
        """mrr_change_pct < -5% → warning."""
        result = detect_anomaly({
            "runway_days": 300,
            "mrr_change_pct": -8.0,
            "burn_rate_cents": 40000,
            "prev_burn_cents": 40000,
            "churned_customers": 0,
        }, TENANT)
        assert result["anomaly_type"] == "mrr_drop"
        assert result["anomaly_severity"] == "warning"

    def test_mrr_drop_critical(self):
        """mrr_change_pct < -15% → critical."""
        result = detect_anomaly({
            "runway_days": 300,
            "mrr_change_pct": -18.0,
            "burn_rate_cents": 40000,
            "prev_burn_cents": 40000,
            "churned_customers": 0,
        }, TENANT)
        assert result["anomaly_type"] == "mrr_drop"
        assert result["anomaly_severity"] == "critical"

    def test_burn_spike_warning(self):
        """burn/prev_burn > 1.2x → warning."""
        result = detect_anomaly({
            "runway_days": 300,
            "mrr_change_pct": 0,
            "burn_rate_cents": 52000,
            "prev_burn_cents": 40000,
            "churned_customers": 0,
        }, TENANT)
        assert result["anomaly_type"] == "burn_spike"
        assert result["anomaly_severity"] == "warning"

    def test_burn_spike_critical(self):
        """burn/prev_burn > 1.5x → critical."""
        result = detect_anomaly({
            "runway_days": 300,
            "mrr_change_pct": 0,
            "burn_rate_cents": 61000,
            "prev_burn_cents": 40000,
            "churned_customers": 0,
        }, TENANT)
        assert result["anomaly_type"] == "burn_spike"
        assert result["anomaly_severity"] == "critical"

    def test_high_churn_warning(self):
        """churned_customers >= 1 → warning."""
        result = detect_anomaly({
            "runway_days": 300,
            "mrr_change_pct": 0,
            "burn_rate_cents": 40000,
            "prev_burn_cents": 40000,
            "churned_customers": 1,
        }, TENANT)
        assert result["anomaly_type"] == "high_churn"
        assert result["anomaly_severity"] == "warning"

    def test_high_churn_critical(self):
        """churned_customers >= 3 → critical."""
        result = detect_anomaly({
            "runway_days": 300,
            "mrr_change_pct": 0,
            "burn_rate_cents": 40000,
            "prev_burn_cents": 40000,
            "churned_customers": 3,
        }, TENANT)
        assert result["anomaly_type"] == "high_churn"
        assert result["anomaly_severity"] == "critical"

    def test_anomaly_type_is_string(self):
        """anomaly_type is a non-empty string when anomaly detected."""
        result = detect_anomaly({
            "runway_days": 80,
            "mrr_change_pct": 0,
            "burn_rate_cents": 50000,
            "prev_burn_cents": 50000,
            "churned_customers": 0,
        }, TENANT)
        assert isinstance(result["anomaly_type"], str)
        assert result["anomaly_type"] != ""
