"""Self-Guardian tests — pure Python, zero infra.

Tests cover schemas, ObservationCollector, and SelfGuardianDetector
following the test_control_plane.py pattern.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from src.schemas.self_guardian import (
    AgentObservation,
    DeviationType,
    SelfGuardianAlert,
    SelfGuardianReport,
)
from src.self_guardian.monitor import ObservationCollector
from src.self_guardian.detector import SelfGuardianDetector


# ---------------------------------------------------------------------------
# Schema Tests
# ---------------------------------------------------------------------------

class TestAgentObservationSchema:
    def test_valid_observation(self):
        now = datetime.now()
        obs = AgentObservation(
            agent_name="Sarthi · Finance",
            action="execute_tool",
            tool_id="pause_failed_payment_retry",
            target_entity="payment:sub_abc123",
            timestamp=now,
            trace_id="trace-001",
            duration_ms=150,
            success=True,
        )
        assert obs.agent_name == "Sarthi · Finance"
        assert obs.action == "execute_tool"
        assert obs.tool_id == "pause_failed_payment_retry"
        assert obs.target_entity == "payment:sub_abc123"
        assert obs.timestamp == now
        assert obs.trace_id == "trace-001"
        assert obs.duration_ms == 150
        assert obs.success is True
        assert obs.error_message is None

    def test_observation_with_error(self):
        obs = AgentObservation(
            agent_name="Sarthi · Ops",
            action="execute_tool",
            tool_id="flag_churn_risk_customer",
            target_entity="customer:xyz",
            timestamp=datetime.now(),
            trace_id="trace-002",
            duration_ms=5000,
            success=False,
            error_message="Timeout connecting to CRM",
        )
        assert obs.success is False
        assert obs.error_message == "Timeout connecting to CRM"

    def test_observation_without_optional_fields(self):
        """tool_id and error_message should be optional."""
        obs = AgentObservation(
            agent_name="Sarthi · Finance",
            action="llm_invoke",
            target_entity="alert:FG-05",
            timestamp=datetime.now(),
            trace_id="trace-003",
            duration_ms=320,
            success=True,
        )
        assert obs.tool_id is None
        assert obs.error_message is None

    def test_missing_required_fields_raises_error(self):
        with pytest.raises(ValidationError):
            AgentObservation(
                agent_name="Sarthi",
                # missing action
                target_entity="something",
                timestamp=datetime.now(),
                trace_id="trace-004",
                duration_ms=100,
                success=True,
            )


class TestDeviationType:
    def test_enum_values(self):
        assert DeviationType.UNAUTHORIZED_TOOL.value == "unauthorized_tool"
        assert DeviationType.DATA_CLASSIFICATION_MISMATCH.value == "data_classification_mismatch"
        assert DeviationType.EXTERNAL_FACING_VIOLATION.value == "external_facing_violation"
        assert DeviationType.STATE_CORRUPTION.value == "state_corruption"
        assert DeviationType.CONFIDENCE_DROP.value == "confidence_drop"
        assert DeviationType.RATE_LIMIT_EXCEEDED.value == "rate_limit_exceeded"

    def test_enum_membership(self):
        assert "unauthorized_tool" in {e.value for e in DeviationType}
        assert "unknown_type" not in {e.value for e in DeviationType}


class TestSelfGuardianAlertSchema:
    def test_valid_alert(self):
        now = datetime.now()
        obs = AgentObservation(
            agent_name="Sarthi · Finance",
            action="execute_tool",
            tool_id="unknown_tool",
            target_entity="payment:sub_abc",
            timestamp=now,
            trace_id="trace-010",
            duration_ms=100,
            success=False,
        )
        alert = SelfGuardianAlert(
            observation=obs,
            deviation=DeviationType.UNAUTHORIZED_TOOL,
            severity="critical",
            description="Unauthorized tool used by agent",
            suggested_action="Revoke and investigate",
        )
        assert alert.observation.agent_name == "Sarthi · Finance"
        assert alert.deviation == DeviationType.UNAUTHORIZED_TOOL
        assert alert.severity == "critical"
        assert alert.description == "Unauthorized tool used by agent"
        assert alert.suggested_action == "Revoke and investigate"

    def test_invalid_severity_raises_error(self):
        now = datetime.now()
        obs = AgentObservation(
            agent_name="Sarthi",
            action="test",
            target_entity="test",
            timestamp=now,
            trace_id="trace-011",
            duration_ms=50,
            success=True,
        )
        with pytest.raises(ValidationError):
            SelfGuardianAlert(
                observation=obs,
                deviation=DeviationType.UNAUTHORIZED_TOOL,
                severity="unknown",  # not one of info/warning/critical
                description="test",
                suggested_action="test",
            )


class TestSelfGuardianReportSchema:
    def test_valid_report(self):
        now = datetime.now()
        obs = AgentObservation(
            agent_name="Sarthi · Finance",
            action="execute_tool",
            tool_id="pause_failed_payment_retry",
            target_entity="payment:sub_abc",
            timestamp=now,
            trace_id="trace-020",
            duration_ms=200,
            success=True,
        )
        alert = SelfGuardianAlert(
            observation=obs,
            deviation=DeviationType.UNAUTHORIZED_TOOL,
            severity="critical",
            description="Test alert",
            suggested_action="Test action",
        )
        report = SelfGuardianReport(
            window_start=now - timedelta(hours=1),
            window_end=now,
            total_observations=1,
            deviations=[alert],
            agent_summaries={
                "Sarthi · Finance": {
                    "total": 1,
                    "deviations": 1,
                    "avg_duration_ms": 200.0,
                },
            },
        )
        assert report.total_observations == 1
        assert len(report.deviations) == 1
        assert report.agent_summaries["Sarthi · Finance"]["deviations"] == 1

    def test_report_default_factory(self):
        now = datetime.now()
        report = SelfGuardianReport(
            window_start=now,
            window_end=now,
            total_observations=0,
        )
        assert report.deviations == []
        assert report.agent_summaries == {}


# ---------------------------------------------------------------------------
# ObservationCollector Tests
# ---------------------------------------------------------------------------

class TestObservationCollector:
    def test_record_and_get_observations(self):
        collector = ObservationCollector()
        now = datetime.now()
        obs = AgentObservation(
            agent_name="Sarthi · Finance",
            action="execute_tool",
            target_entity="payment:sub_abc",
            timestamp=now,
            trace_id="trace-100",
            duration_ms=100,
            success=True,
        )
        collector.record_observation(obs)
        results = collector.get_observations()
        assert len(results) == 1
        assert results[0].trace_id == "trace-100"

    def test_get_observations_filter_by_agent(self):
        collector = ObservationCollector()
        now = datetime.now()
        obs1 = AgentObservation(
            agent_name="Finance",
            action="execute_tool",
            target_entity="payment:x",
            timestamp=now,
            trace_id="trace-101",
            duration_ms=100,
            success=True,
        )
        obs2 = AgentObservation(
            agent_name="Ops",
            action="execute_tool",
            target_entity="customer:y",
            timestamp=now,
            trace_id="trace-102",
            duration_ms=200,
            success=True,
        )
        collector.record_observation(obs1)
        collector.record_observation(obs2)
        finance_obs = collector.get_observations(agent_name="Finance")
        assert len(finance_obs) == 1
        assert finance_obs[0].agent_name == "Finance"
        ops_obs = collector.get_observations(agent_name="Ops")
        assert len(ops_obs) == 1

    def test_get_observations_filter_by_since(self):
        collector = ObservationCollector()
        early = datetime(2025, 1, 1, 10, 0, 0)
        late = datetime(2025, 1, 1, 12, 0, 0)
        obs1 = AgentObservation(
            agent_name="Sarthi",
            action="test",
            target_entity="x",
            timestamp=early,
            trace_id="trace-103",
            duration_ms=100,
            success=True,
        )
        obs2 = AgentObservation(
            agent_name="Sarthi",
            action="test",
            target_entity="y",
            timestamp=late,
            trace_id="trace-104",
            duration_ms=100,
            success=True,
        )
        collector.record_observation(obs1)
        collector.record_observation(obs2)
        cutoff = datetime(2025, 1, 1, 11, 0, 0)
        results = collector.get_observations(since=cutoff)
        assert len(results) == 1
        assert results[0].trace_id == "trace-104"

    def test_clear(self):
        collector = ObservationCollector()
        now = datetime.now()
        obs = AgentObservation(
            agent_name="Sarthi",
            action="test",
            target_entity="x",
            timestamp=now,
            trace_id="trace-105",
            duration_ms=100,
            success=True,
        )
        collector.record_observation(obs)
        assert collector.count == 1
        collector.clear()
        assert collector.count == 0

    def test_buffer_cap(self):
        """Buffer should not exceed 10000 entries; oldest are evicted."""
        collector = ObservationCollector()
        now = datetime.now()
        # Record 10001 observations
        for i in range(10001):
            obs = AgentObservation(
                agent_name="Sarthi",
                action=f"action_{i}",
                target_entity=f"entity_{i}",
                timestamp=now + timedelta(seconds=i),
                trace_id=f"trace-bulk-{i}",
                duration_ms=i,
                success=True,
            )
            collector.record_observation(obs)
        assert collector.count == 10000
        # The oldest (trace-bulk-0) should be evicted
        results = collector.get_observations()
        trace_ids = [r.trace_id for r in results]
        assert "trace-bulk-0" not in trace_ids
        assert "trace-bulk-10000" in trace_ids

    def test_thread_safety(self):
        """Observations recorded from multiple threads should all be visible."""
        import threading

        collector = ObservationCollector()
        now = datetime.now()
        n = 100
        results_list: list[Exception | None] = []
        lock = threading.Lock()

        def record_obs(idx: int):
            try:
                obs = AgentObservation(
                    agent_name=f"Agent-{idx}",
                    action="concurrent_test",
                    target_entity=f"entity-{idx}",
                    timestamp=now,
                    trace_id=f"trace-concurrent-{idx}",
                    duration_ms=idx,
                    success=True,
                )
                collector.record_observation(obs)
                with lock:
                    results_list.append(None)
            except Exception as e:
                with lock:
                    results_list.append(e)

        threads = [threading.Thread(target=record_obs, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r is None for r in results_list), "Some threads raised exceptions"
        assert collector.count == n
        assert len(collector.get_observations()) == n


# ---------------------------------------------------------------------------
# SelfGuardianDetector Tests
# ---------------------------------------------------------------------------

class TestSelfGuardianDetector:
    def test_unauthorized_tool_detected(self):
        """Using a tool not in the agent's allowed_tool_ids should alert."""
        detector = SelfGuardianDetector()
        now = datetime.now()
        # "Sarthi · Finance" only has "pause_failed_payment_retry"
        obs = AgentObservation(
            agent_name="Sarthi · Finance",
            action="execute_tool",
            tool_id="unauthorized_tool_xyz",
            target_entity="payment:test",
            timestamp=now,
            trace_id="trace-200",
            duration_ms=100,
            success=True,
        )
        alert = detector.analyze(obs)
        assert alert is not None
        assert alert.deviation == DeviationType.UNAUTHORIZED_TOOL
        assert alert.severity == "critical"
        assert "unauthorized_tool_xyz" in alert.description

    def test_authorized_tool_no_alert(self):
        """Using an allowed tool should not trigger an unauthorized tool alert."""
        detector = SelfGuardianDetector()
        now = datetime.now()
        obs = AgentObservation(
            agent_name="Sarthi · Finance",
            action="execute_tool",
            tool_id="pause_failed_payment_retry",
            target_entity="payment:sub_abc",
            timestamp=now,
            trace_id="trace-201",
            duration_ms=100,
            success=True,
        )
        alert = detector.analyze(obs)
        # May still trigger other checks, but should NOT trigger unauthorized_tool
        if alert is not None:
            assert alert.deviation != DeviationType.UNAUTHORIZED_TOOL

    def test_unknown_agent_no_tool_alert(self):
        """Unknown agents have no allowed tools — any tool use is unauthorized."""
        detector = SelfGuardianDetector()
        now = datetime.now()
        obs = AgentObservation(
            agent_name="UnknownAgent",
            action="execute_tool",
            tool_id="some_tool",
            target_entity="test",
            timestamp=now,
            trace_id="trace-202",
            duration_ms=50,
            success=True,
        )
        alert = detector.analyze(obs)
        assert alert is not None
        assert alert.deviation == DeviationType.UNAUTHORIZED_TOOL

    def test_external_facing_violation_detected(self):
        """Sarthi is external_facing=True — accessing internal data should alert."""
        detector = SelfGuardianDetector()
        now = datetime.now()
        obs = AgentObservation(
            agent_name="Sarthi",
            action="read_internal_report",
            target_entity="internal_pii_record",
            timestamp=now,
            trace_id="trace-203",
            duration_ms=100,
            success=True,
        )
        alert = detector.analyze(obs)
        assert alert is not None
        assert alert.deviation == DeviationType.EXTERNAL_FACING_VIOLATION
        assert alert.severity == "warning"

    def test_external_facing_safe_action_no_alert(self):
        """Sarthi external action without internal keywords should pass."""
        detector = SelfGuardianDetector()
        now = datetime.now()
        obs = AgentObservation(
            agent_name="Sarthi",
            action="generate_investor_update",
            target_entity="investor_relations",
            timestamp=now,
            trace_id="trace-204",
            duration_ms=100,
            success=True,
        )
        alert = detector.analyze(obs)
        # Should not be external_facing_violation
        if alert is not None:
            assert alert.deviation != DeviationType.EXTERNAL_FACING_VIOLATION

    def test_successful_observation_returns_none(self):
        """A clean successful observation from an internal agent should return None."""
        detector = SelfGuardianDetector()
        now = datetime.now()
        obs = AgentObservation(
            agent_name="Sarthi · Finance",
            action="execute_tool",
            tool_id="pause_failed_payment_retry",
            target_entity="payment:sub_abc",
            timestamp=now,
            trace_id="trace-205",
            duration_ms=100,
            success=True,
        )
        alert = detector.analyze(obs)
        assert alert is None

    def test_failed_observation_returns_alert(self):
        """A failed observation should trigger a state_corruption alert."""
        detector = SelfGuardianDetector()
        now = datetime.now()
        obs = AgentObservation(
            agent_name="Sarthi · Finance",
            action="execute_tool",
            tool_id="pause_failed_payment_retry",
            target_entity="payment:sub_abc",
            timestamp=now,
            trace_id="trace-206",
            duration_ms=5000,
            success=False,
            error_message="Payment gateway timeout",
        )
        alert = detector.analyze(obs)
        assert alert is not None
        assert alert.deviation == DeviationType.STATE_CORRUPTION
        assert alert.severity == "info"
        assert "Payment gateway timeout" in alert.description

    def test_generate_report_with_empty_list(self):
        """Empty observations should yield an empty report."""
        detector = SelfGuardianDetector()
        report = detector.generate_report([])
        assert report.total_observations == 0
        assert report.deviations == []
        assert report.agent_summaries == {}

    def test_generate_report_with_observations(self):
        """Report should aggregate observations and detected deviations."""
        detector = SelfGuardianDetector()
        now = datetime.now()

        obs1 = AgentObservation(
            agent_name="Sarthi · Finance",
            action="execute_tool",
            tool_id="pause_failed_payment_retry",
            target_entity="payment:sub_abc",
            timestamp=now - timedelta(minutes=10),
            trace_id="trace-300",
            duration_ms=150,
            success=True,
        )
        obs2 = AgentObservation(
            agent_name="Sarthi · Finance",
            action="execute_tool",
            tool_id="unauthorized_tool",
            target_entity="payment:sub_xyz",
            timestamp=now - timedelta(minutes=5),
            trace_id="trace-301",
            duration_ms=100,
            success=True,
        )
        obs3 = AgentObservation(
            agent_name="Sarthi · Ops",
            action="execute_tool",
            tool_id="flag_churn_risk_customer",
            target_entity="customer:123",
            timestamp=now,
            trace_id="trace-302",
            duration_ms=200,
            success=False,
            error_message="API error",
        )

        report = detector.generate_report([obs1, obs2, obs3])
        assert report.total_observations == 3
        assert len(report.deviations) == 2  # obs2 (unauthorized) + obs3 (failure)

        # Check agent summaries
        assert "Sarthi · Finance" in report.agent_summaries
        assert "Sarthi · Ops" in report.agent_summaries
        assert report.agent_summaries["Sarthi · Finance"]["total"] == 2
        assert report.agent_summaries["Sarthi · Finance"]["deviations"] == 1
        assert report.agent_summaries["Sarthi · Ops"]["total"] == 1
        assert report.agent_summaries["Sarthi · Ops"]["deviations"] == 1

        # Check window bounds
        assert report.window_start <= report.window_end
