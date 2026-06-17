"""Trajectory verification tests for Startup Guardian orchestrator.

These tests verify that the orchestrator follows expected trajectories:
1. Connectors are called in the correct order
2. Assemblers process raw snapshots correctly
3. Overall health is computed from domain healths
4. Watchlists fire the correct alerts
5. Correlations detect cross-domain patterns

All tests use mocks — no Docker containers or API calls required.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from tests.deterministic.golden_trajectories import (
    GOLDEN_TRAJECTORIES,
    TrajectoryScenario,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_connector_side_effect(
    scenario: TrajectoryScenario,
    call_log: list[str],
) -> dict[str, MagicMock]:
    """Create MagicMock connectors that record call order and return scenario data."""
    connectors: dict[str, MagicMock] = {}
    for name in scenario.connector_order:
        if name in scenario.raw_snapshots:
            snap = scenario.raw_snapshots[name]

            def _factory(*_args: Any, snap=snap, log=call_log, _name=name, **_kw: Any) -> Any:
                log.append(_name)
                return snap

            connectors[name] = MagicMock(side_effect=_factory)
        else:
            # Connector should fail
            def _fail_factory(*_args: Any, log=call_log, _name=name, **_kw: Any) -> Any:
                log.append(_name)
                raise ConnectionError(f"{_name} connector failed")

            connectors[name] = MagicMock(side_effect=_fail_factory)
    return connectors


def _run_orchestrator_sync(
    scenario: TrajectoryScenario,
) -> dict[str, Any]:
    """Run the orchestrator synchronously with mocked connectors.

    Returns the state dict produced by run_startup_guardian.

    The orchestrator stores connector function references in ``_CONNECTORS``
    at import time. Patching module-level names doesn't affect the list,
    so we swap ``_CONNECTORS`` directly on the module object.
    """
    call_log: list[str] = []
    connectors = _make_connector_side_effect(scenario, call_log)

    async def _run() -> dict[str, Any]:
        import src.orchestration.run_startup_guardian as mod

        mock_erpnext = connectors.get(
            "erpnext", MagicMock(side_effect=ConnectionError("erpnext not in scenario"))
        )
        mock_hubspot = connectors.get(
            "hubspot", MagicMock(side_effect=ConnectionError("hubspot not in scenario"))
        )
        mock_quickbooks = connectors.get(
            "quickbooks", MagicMock(side_effect=ConnectionError("quickbooks not in scenario"))
        )

        patched_connectors = [
            ("erpnext", mock_erpnext),
            ("hubspot", mock_hubspot),
            ("quickbooks", mock_quickbooks),
        ]

        # Swap _CONNECTORS so the orchestrator iterates our mocks
        original_connectors = mod._CONNECTORS
        mod._CONNECTORS = patched_connectors
        try:
            result = await mod.run_startup_guardian("test-tenant")
        finally:
            mod._CONNECTORS = original_connectors

        result["_call_log"] = call_log
        return result

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_run())
    finally:
        loop.close()


def _extract_alert_ids(state: dict[str, Any]) -> list[str]:
    """Run watchlists on a state dict and return alert IDs."""
    from src.guardian.startup_watchlists import run_watchlists

    alerts = run_watchlists(state)
    return [a["id"] for a in alerts]


def _extract_correlation_ids(state: dict[str, Any]) -> list[str]:
    """Run correlations on a state dict and return correlation IDs."""
    from src.guardian.startup_correlations import run_correlations

    corrs = run_correlations(state)
    return [c["id"] for c in corrs]


# ---------------------------------------------------------------------------
# Parametrized tests — one per golden trajectory
# ---------------------------------------------------------------------------


class TestGoldenTrajectories:
    """Verify each golden trajectory produces the expected orchestrator behavior."""

    @pytest.mark.parametrize(
        "scenario",
        GOLDEN_TRAJECTORIES,
        ids=[s.name for s in GOLDEN_TRAJECTORIES],
    )
    def test_connector_order(self, scenario: TrajectoryScenario) -> None:
        """Connectors are called in the expected order."""
        result = _run_orchestrator_sync(scenario)
        actual_order = result["_call_log"]
        assert actual_order == scenario.connector_order, (
            f"[{scenario.name}] Connector call order mismatch: "
            f"expected {scenario.connector_order}, got {actual_order}"
        )

    @pytest.mark.parametrize(
        "scenario",
        GOLDEN_TRAJECTORIES,
        ids=[s.name for s in GOLDEN_TRAJECTORIES],
    )
    def test_connectors_ok(self, scenario: TrajectoryScenario) -> None:
        """connectors_ok matches expected health for each connector."""
        result = _run_orchestrator_sync(scenario)
        for name, expected_ok in scenario.connectors_ok.items():
            assert result["connectors_ok"].get(name) == expected_ok, (
                f"[{scenario.name}] connectors_ok[{name}] expected {expected_ok}, "
                f"got {result['connectors_ok'].get(name)}"
            )

    @pytest.mark.parametrize(
        "scenario",
        GOLDEN_TRAJECTORIES,
        ids=[s.name for s in GOLDEN_TRAJECTORIES],
    )
    def test_overall_health(self, scenario: TrajectoryScenario) -> None:
        """overall_health matches the expected value."""
        result = _run_orchestrator_sync(scenario)
        assert result["overall_health"] == scenario.expected_health, (
            f"[{scenario.name}] overall_health expected '{scenario.expected_health}', "
            f"got '{result['overall_health']}'"
        )

    @pytest.mark.parametrize(
        "scenario",
        GOLDEN_TRAJECTORIES,
        ids=[s.name for s in GOLDEN_TRAJECTORIES],
    )
    def test_raw_snapshots_stored(self, scenario: TrajectoryScenario) -> None:
        """raw_snapshots in state match what connectors returned."""
        result = _run_orchestrator_sync(scenario)
        for name, expected_snap in scenario.raw_snapshots.items():
            assert name in result["raw_snapshots"], (
                f"[{scenario.name}] raw_snapshots missing connector '{name}'"
            )
            # Check key fields (not metadata like source/fetched_at)
            for key, val in expected_snap.items():
                assert result["raw_snapshots"][name].get(key) == val, (
                    f"[{scenario.name}] raw_snapshots[{name}][{key}] "
                    f"expected {val}, got {result['raw_snapshots'][name].get(key)}"
                )


class TestWatchlistAlerts:
    """Verify watchlists fire the correct alerts for each scenario."""

    @pytest.mark.parametrize(
        "scenario",
        GOLDEN_TRAJECTORIES,
        ids=[s.name for s in GOLDEN_TRAJECTORIES],
    )
    def test_expected_alerts(self, scenario: TrajectoryScenario) -> None:
        """Watchlists produce exactly the expected alert IDs."""
        result = _run_orchestrator_sync(scenario)
        actual_alerts = sorted(_extract_alert_ids(result))
        expected_alerts = sorted(scenario.expected_alerts)
        assert actual_alerts == expected_alerts, (
            f"[{scenario.name}] Alert mismatch: "
            f"expected {expected_alerts}, got {actual_alerts}"
        )


class TestCorrelations:
    """Verify cross-domain correlations fire for each scenario."""

    @pytest.mark.parametrize(
        "scenario",
        GOLDEN_TRAJECTORIES,
        ids=[s.name for s in GOLDEN_TRAJECTORIES],
    )
    def test_expected_correlations(self, scenario: TrajectoryScenario) -> None:
        """Correlations produce exactly the expected correlation IDs."""
        result = _run_orchestrator_sync(scenario)
        actual_corrs = sorted(_extract_correlation_ids(result))
        expected_corrs = sorted(scenario.expected_correlations)
        assert actual_corrs == expected_corrs, (
            f"[{scenario.name}] Correlation mismatch: "
            f"expected {expected_corrs}, got {actual_corrs}"
        )


class TestAssemblyCorrectness:
    """Verify assemblers transform raw snapshots into correct domain states."""

    def test_support_state_assembly(self) -> None:
        """Support assembler maps unresolved_issues > 5 to CRITICAL."""
        from src.guardian.assemblers import assemble_support_state

        raw = {"support_open_issues": 25, "support_unresolved_issues": 20}
        state = assemble_support_state(raw)
        assert state.open_issues == 25
        assert state.unresolved_issues == 20
        assert state.health.value == "critical"

    def test_support_state_good(self) -> None:
        """Support assembler maps unresolved_issues == 0 to GOOD."""
        from src.guardian.assemblers import assemble_support_state

        raw = {"support_open_issues": 5, "support_unresolved_issues": 0}
        state = assemble_support_state(raw)
        assert state.health.value == "good"

    def test_execution_state_blocked(self) -> None:
        """Execution assembler maps overdue_tasks > 3 to BLOCKED."""
        from src.guardian.assemblers import assemble_execution_state

        raw = {"execution_overdue_tasks": 7, "execution_active_projects": 4}
        state = assemble_execution_state(raw)
        assert state.health.value == "blocked"

    def test_execution_state_on_track(self) -> None:
        """Execution assembler maps overdue_tasks == 0 to ON_TRACK."""
        from src.guardian.assemblers import assemble_execution_state

        raw = {"execution_overdue_tasks": 0, "execution_active_projects": 3}
        state = assemble_execution_state(raw)
        assert state.health.value == "on_track"

    def test_finance_state_critical(self) -> None:
        """Finance assembler maps overdue > 1M cents to CRITICAL."""
        from src.guardian.assemblers import assemble_finance_state

        raw = {"finance_overdue_cents": 2_000_000, "finance_total_outstanding_cents": 5_000_000}
        state = assemble_finance_state(raw)
        assert state.health.value == "critical"

    def test_finance_state_healthy(self) -> None:
        """Finance assembler maps overdue == 0 to HEALTHY."""
        from src.guardian.assemblers import assemble_finance_state

        raw = {"finance_overdue_cents": 0, "finance_total_outstanding_cents": 100_000}
        state = assemble_finance_state(raw)
        assert state.health.value == "healthy"

    def test_revenue_state_declining(self) -> None:
        """Revenue assembler detects declining trend when won=0 and pipeline>0."""
        from src.guardian.assemblers import assemble_revenue_state

        raw = {
            "revenue_won_deals_30d_cents": 0,
            "revenue_pipeline_deals_cents": 500_000_00,
        }
        state = assemble_revenue_state(raw)
        assert state.trend.value == "declining"

    def test_revenue_state_growing(self) -> None:
        """Revenue assembler detects growing trend when won > 30% of pipeline."""
        from src.guardian.assemblers import assemble_revenue_state

        raw = {
            "revenue_won_deals_30d_cents": 200_000_00,
            "revenue_pipeline_deals_cents": 300_000_00,
        }
        state = assemble_revenue_state(raw)
        assert state.trend.value == "growing"

    def test_team_state_critical(self) -> None:
        """Team assembler maps departures > 2 to CRITICAL."""
        from src.guardian.assemblers import assemble_team_state

        raw = {"team_departures_30d": 5, "team_active_count": 15}
        state = assemble_team_state(raw)
        assert state.health.value == "critical"

    def test_team_state_good(self) -> None:
        """Team assembler maps departures == 0 to GOOD."""
        from src.guardian.assemblers import assemble_team_state

        raw = {"team_departures_30d": 0, "team_active_count": 15}
        state = assemble_team_state(raw)
        assert state.health.value == "good"


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_snapshots_all_defaults(self) -> None:
        """Empty raw snapshots produce default/healthy domain states."""
        from src.guardian.assemblers import (
            assemble_execution_state,
            assemble_finance_state,
            assemble_support_state,
            assemble_team_state,
        )

        assert assemble_support_state({}).health.value == "good"
        assert assemble_execution_state({}).health.value == "on_track"
        assert assemble_finance_state({}).health.value == "healthy"
        assert assemble_team_state({}).health.value == "good"

    def test_all_connectors_fail_returns_defaults(self) -> None:
        """When all connectors fail, state has all defaults and health=good."""
        scenario = GOLDEN_TRAJECTORIES[7]  # all_fail
        result = _run_orchestrator_sync(scenario)
        assert result["overall_health"] == "good"
        assert result["support"]["health"] == "good"
        assert result["execution"]["health"] == "on_track"
        assert result["finance"]["health"] == "healthy"
        assert result["team"]["health"] == "good"

    def test_quickbooks_overwrites_erpnext_finance(self) -> None:
        """QuickBooks finance assembly overwrites ERPNext finance assembly."""
        scenario = GOLDEN_TRAJECTORIES[0]  # all_healthy
        result = _run_orchestrator_sync(scenario)
        # QuickBooks snapshot has finance_days_sales_outstanding=33.0
        # which ERPNext doesn't set — confirms QuickBooks ran last
        assert result["finance"]["days_sales_outstanding"] == 33.0

    def test_deterministic_same_input_same_output(self) -> None:
        """Running the same scenario twice produces identical results."""
        scenario = GOLDEN_TRAJECTORIES[0]
        r1 = _run_orchestrator_sync(scenario)
        r2 = _run_orchestrator_sync(scenario)
        # Compare domain healths (skip run_id/timestamp)
        assert r1["overall_health"] == r2["overall_health"]
        assert r1["support"]["health"] == r2["support"]["health"]
        assert r1["execution"]["health"] == r2["execution"]["health"]
        assert r1["finance"]["health"] == r2["finance"]["health"]
        assert r1["team"]["health"] == r2["team"]["health"]
        assert r1["connectors_ok"] == r2["connectors_ok"]
