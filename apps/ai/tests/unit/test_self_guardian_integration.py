"""Self-Guardian Integration tests — mocked persister and detector.

Tests verify:
1. record_agent_action creates observation, runs detector, persists alert + observation
2. run_self_check returns a SelfGuardianReport
3. Context manager (async with) lifecycle works correctly
4. record_alert persists alerts to DB
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.schemas.self_guardian import (
    AgentObservation,
    DeviationType,
    SelfGuardianAlert,
    SelfGuardianReport,
)
from src.self_guardian.integration import SelfGuardianIntegration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_persister() -> MagicMock:
    """Return a mock SelfGuardianPersister with async methods."""
    persister = MagicMock()
    persister.store_observation = AsyncMock()
    persister.store_alert = AsyncMock()
    persister.get_recent_alerts = AsyncMock(return_value=[])
    persister.get_agent_summary = AsyncMock(return_value=[])
    persister.close = AsyncMock()
    return persister


@pytest.fixture
def sample_observation() -> AgentObservation:
    """Return a valid AgentObservation for testing."""
    return AgentObservation(
        agent_name="FP&A",
        action="execute_tool",
        tool_id="pause_failed_payment_retry",
        target_entity="payment:sub_abc123",
        timestamp=datetime(2025, 6, 1, 12, 0, 0),
        trace_id="trace-int-001",
        duration_ms=150,
        success=True,
    )


@pytest.fixture
def sample_alert(sample_observation: AgentObservation) -> SelfGuardianAlert:
    """Return a valid SelfGuardianAlert for testing."""
    return SelfGuardianAlert(
        observation=sample_observation,
        deviation=DeviationType.UNAUTHORIZED_TOOL,
        severity="critical",
        description="Agent used an unauthorized tool.",
        suggested_action="Revoke and investigate.",
    )


# ---------------------------------------------------------------------------
# SelfGuardianIntegration Tests
# ---------------------------------------------------------------------------

class TestRecordAgentAction:
    """Tests for ``SelfGuardianIntegration.record_agent_action``."""

    async def test_calls_persister_store_observation(
        self,
        mock_persister: MagicMock,
    ):
        """Should create an observation and persist it via the persister."""
        integration = SelfGuardianIntegration(persister=mock_persister)

        await integration.record_agent_action(
            agent_name="FP&A",
            action="execute_tool",
            tool_id="pause_failed_payment_retry",
            target_entity="payment:sub_abc",
            success=True,
            trace_id="trace-test-001",
            duration_ms=200,
        )

        # Observation should be stored in the in-memory collector
        assert integration.collector.count == 1

        # Persister store_observation should have been called
        mock_persister.store_observation.assert_awaited_once()
        obs_arg = mock_persister.store_observation.call_args[0][0]
        assert isinstance(obs_arg, AgentObservation)
        assert obs_arg.agent_name == "FP&A"
        assert obs_arg.action == "execute_tool"

    async def test_clean_observation_no_alert_stored(
        self,
        mock_persister: MagicMock,
    ):
        """A clean observation (no deviation) should not store an alert."""
        integration = SelfGuardianIntegration(persister=mock_persister)

        alert = await integration.record_agent_action(
            agent_name="FP&A",
            action="execute_tool",
            tool_id="pause_failed_payment_retry",
            target_entity="payment:sub_abc",
            success=True,
            trace_id="trace-clean-001",
            duration_ms=100,
        )

        # No deviation should be detected for allowed tool use
        assert alert is None

        # Observation should still be persisted
        mock_persister.store_observation.assert_awaited_once()

        # Alert should NOT have been stored
        mock_persister.store_alert.assert_not_called()

    async def test_deviation_stores_alert(
        self,
        mock_persister: MagicMock,
    ):
        """An observation with a deviation should store both observation and alert."""
        integration = SelfGuardianIntegration(persister=mock_persister)

        alert = await integration.record_agent_action(
            agent_name="FP&A",
            action="execute_tool",
            tool_id="unauthorized_tool_xyz",  # Not in allowed tools for Finance
            target_entity="payment:sub_abc",
            success=True,
            trace_id="trace-dev-001",
            duration_ms=100,
        )

        # Deviation should be detected
        assert alert is not None
        assert alert.deviation == DeviationType.UNAUTHORIZED_TOOL

        # Both observation and alert should be persisted
        mock_persister.store_observation.assert_awaited_once()
        mock_persister.store_alert.assert_awaited_once()

    async def test_record_with_auto_generated_trace_id(
        self,
        mock_persister: MagicMock,
    ):
        """When trace_id is not provided, one should be auto-generated."""
        integration = SelfGuardianIntegration(persister=mock_persister)

        await integration.record_agent_action(
            agent_name="Reliability & Delivery",
            action="execute_tool",
            tool_id="flag_churn_risk_customer",
            target_entity="customer:xyz",
            success=False,
            error_message="API timeout",
            duration_ms=5000,
        )

        mock_persister.store_observation.assert_awaited_once()
        obs_arg = mock_persister.store_observation.call_args[0][0]
        assert obs_arg.trace_id is not None
        assert isinstance(obs_arg.trace_id, str)
        assert len(obs_arg.trace_id) > 0

    async def test_closed_integration_skips_recording(
        self,
        mock_persister: MagicMock,
    ):
        """After close(), record_agent_action should be a no-op."""
        integration = SelfGuardianIntegration(persister=mock_persister)
        await integration.close()

        result = await integration.record_agent_action(
            agent_name="Chief of Staff",
            action="test",
            target_entity="test",
            success=True,
        )

        assert result is None
        mock_persister.store_observation.assert_not_called()
        mock_persister.store_alert.assert_not_called()


class TestRecordAlert:
    """Tests for ``SelfGuardianIntegration.record_alert``."""

    async def test_record_alert_persists(
        self,
        mock_persister: MagicMock,
        sample_alert: SelfGuardianAlert,
    ):
        """record_alert should delegate to persister.store_alert."""
        integration = SelfGuardianIntegration(persister=mock_persister)
        await integration.record_alert(sample_alert)

        mock_persister.store_alert.assert_awaited_once_with(sample_alert)

    async def test_closed_integration_skips_alert(
        self,
        mock_persister: MagicMock,
        sample_alert: SelfGuardianAlert,
    ):
        """After close(), record_alert should be a no-op."""
        integration = SelfGuardianIntegration(persister=mock_persister)
        await integration.close()

        await integration.record_alert(sample_alert)
        mock_persister.store_alert.assert_not_called()


class TestRunSelfCheck:
    """Tests for ``SelfGuardianIntegration.run_self_check``."""

    async def test_returns_report(
        self,
        mock_persister: MagicMock,
    ):
        """run_self_check should return a SelfGuardianReport."""
        integration = SelfGuardianIntegration(persister=mock_persister)

        # Record some observations first
        await integration.record_agent_action(
            agent_name="FP&A",
            action="execute_tool",
            tool_id="pause_failed_payment_retry",
            target_entity="payment:sub_abc",
            success=True,
        )
        await integration.record_agent_action(
            agent_name="Reliability & Delivery",
            action="execute_tool",
            tool_id="flag_churn_risk_customer",
            target_entity="customer:xyz",
            success=False,
            error_message="CRM timeout",
        )

        report = await integration.run_self_check()

        assert isinstance(report, SelfGuardianReport)
        assert report.total_observations == 2
        assert "FP&A" in report.agent_summaries
        assert "Reliability & Delivery" in report.agent_summaries

    async def test_persists_alerts_on_self_check(
        self,
        mock_persister: MagicMock,
    ):
        """Alerts found during self-check should be persisted."""
        integration = SelfGuardianIntegration(persister=mock_persister)

        # Record a deviant observation
        await integration.record_agent_action(
            agent_name="FP&A",
            action="execute_tool",
            tool_id="unauthorized_tool",
            target_entity="payment:sub_abc",
            success=True,
        )

        # Reset call counts — we only care about run_self_check's persists
        mock_persister.store_alert.reset_mock()

        report = await integration.run_self_check()

        # The deviant observation should be detected
        assert len(report.deviations) >= 1

        # Alerts should have been persisted
        assert mock_persister.store_alert.awaited

    async def test_empty_observations_returns_empty_report(
        self,
        mock_persister: MagicMock,
    ):
        """With no observations, run_self_check should return a zeroed report."""
        integration = SelfGuardianIntegration(persister=mock_persister)

        report = await integration.run_self_check()

        assert report.total_observations == 0
        assert report.deviations == []
        assert report.agent_summaries == {}


class TestContextManager:
    """Tests for async context manager (async with) protocol."""

    async def test_enter_and_exit(self, mock_persister: MagicMock):
        """Async context manager should set up and tear down correctly."""
        async with SelfGuardianIntegration(persister=mock_persister) as sgi:
            assert isinstance(sgi, SelfGuardianIntegration)
            assert not sgi._closed

            # Should be usable inside context
            await sgi.record_agent_action(
                agent_name="Chief of Staff",
                action="test",
                target_entity="test",
                success=True,
            )
            assert sgi.collector.count == 1

        # After exiting, should be closed
        assert sgi._closed
        mock_persister.close.assert_awaited_once()

    async def test_exit_on_exception(self, mock_persister: MagicMock):
        """Context manager should close even if an exception occurs."""
        with pytest.raises(RuntimeError, match="test error"):
            async with SelfGuardianIntegration(persister=mock_persister) as sgi:
                raise RuntimeError("test error")

        # Should still have cleaned up
        assert sgi._closed
        mock_persister.close.assert_awaited_once()

    async def test_multiple_close_is_safe(self, mock_persister: MagicMock):
        """Calling close() multiple times should be safe."""
        integration = SelfGuardianIntegration(persister=mock_persister)
        await integration.close()
        await integration.close()  # second close should be no-op

        mock_persister.close.assert_awaited_once()


class TestWithDetectorAndPersister:
    """Integration-style tests with real detector but mocked persister."""

    async def test_record_agent_action_calls_persister(
        self,
        mock_persister: MagicMock,
    ):
        """Verify the full flow: record → observe → detect → persist."""
        integration = SelfGuardianIntegration(persister=mock_persister)

        await integration.record_agent_action(
            agent_name="FP&A",
            action="execute_tool",
            tool_id="pause_failed_payment_retry",
            target_entity="payment:sub_abc",
            success=True,
            trace_id="trace-flow-001",
            duration_ms=150,
        )

        # Should have persisted the observation
        mock_persister.store_observation.assert_awaited_once()

        # Should NOT have persisted an alert (clean action)
        mock_persister.store_alert.assert_not_called()

        # Observation should be in the in-memory buffer
        obs_list = integration.collector.get_observations()
        assert len(obs_list) == 1
        assert obs_list[0].trace_id == "trace-flow-001"

    async def test_run_self_check_returns_report(
        self,
        mock_persister: MagicMock,
    ):
        """run_self_check should aggregate observations and return a report."""
        integration = SelfGuardianIntegration(persister=mock_persister)

        await integration.record_agent_action(
            agent_name="FP&A",
            action="execute_tool",
            tool_id="pause_failed_payment_retry",
            target_entity="payment:sub_abc",
            success=True,
        )
        await integration.record_agent_action(
            agent_name="FP&A",
            action="execute_tool",
            tool_id="unauthorized_tool",
            target_entity="payment:sub_xyz",
            success=True,
        )

        report = await integration.run_self_check()

        assert isinstance(report, SelfGuardianReport)
        assert report.total_observations == 2
        assert report.agent_summaries["FP&A"]["total"] == 2

    async def test_unauthorized_tool_deviation_detected(
        self,
        mock_persister: MagicMock,
    ):
        """Using an unauthorized tool should trigger and persist an alert."""
        integration = SelfGuardianIntegration(persister=mock_persister)

        alert = await integration.record_agent_action(
            agent_name="FP&A",
            action="execute_tool",
            tool_id="some_random_tool",
            target_entity="payment:sub_abc",
            success=True,
        )

        assert alert is not None
        assert alert.deviation == DeviationType.UNAUTHORIZED_TOOL
        mock_persister.store_alert.assert_awaited_once()

    async def test_failed_action_detected(
        self,
        mock_persister: MagicMock,
    ):
        """A failed action should trigger a state_corruption deviation."""
        integration = SelfGuardianIntegration(persister=mock_persister)

        alert = await integration.record_agent_action(
            agent_name="FP&A",
            action="execute_tool",
            tool_id="pause_failed_payment_retry",
            target_entity="payment:sub_abc",
            success=False,
            error_message="Payment gateway timeout",
        )

        assert alert is not None
        assert alert.deviation == DeviationType.STATE_CORRUPTION
        mock_persister.store_alert.assert_awaited_once()
