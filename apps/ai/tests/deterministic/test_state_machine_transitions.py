"""
Deterministic tests for Startup Guardian state machine transitions.

Covers:
  1. Happy path (all connectors succeed)
  2. Partial failure (one connector fails)
  3. All-fail (all connectors fail)
  4. _map_health() correctness
  5. Health priority ordering (worst wins)
  6. Assembler call order
  7. connectors_ok accuracy
  8. raw_snapshots preservation
  9. run_id uniqueness
 10. tenant_id propagation

No LLM calls. No Docker. All mocked connectors.

IMPORTANT: The orchestrator's _CONNECTORS list captures function references at
import time. We must patch _CONNECTORS directly rather than patching source
modules, because the tuple holds the original function objects.
"""
from __future__ import annotations

import pytest
from unittest.mock import Mock, patch

# ---------------------------------------------------------------------------
# Shared snapshots
# ---------------------------------------------------------------------------

ERPNEXT_SNAPSHOT = {
    "support_open_issues": 8,
    "support_unresolved_issues": 3,
    "execution_active_projects": 2,
    "execution_overdue_tasks": 1,
    "execution_milestones_total": 12,
    "execution_milestones_completed": 5,
    "execution_avg_completion": 42.5,
    "team_active_count": 10,
    "team_departments": {"eng": 5, "sales": 3, "ops": 2},
    "team_new_joinees_30d": 2,
    "team_departures_30d": 1,
    "finance_total_outstanding_cents": 200_000,
    "finance_overdue_cents": 50_000,
    "finance_unpaid_cents": 80_000,
    "finance_outstanding_invoices": 5,
    "finance_overdue_invoices": 1,
    "finance_paid_invoices_30d_cents": 150_000,
    "finance_days_sales_outstanding": 30.0,
}

HUBSPOT_SNAPSHOT = {
    "revenue_total_deals_cents": 500_000,
    "revenue_won_deals_30d_cents": 200_000,
    "revenue_pipeline_deals_cents": 300_000,
    "revenue_active_customers": 12,
    "revenue_mrr_cents": 50_000,
}

QUICKBOOKS_SNAPSHOT = {
    "finance_total_outstanding_cents": 300_000,
    "finance_overdue_cents": 75_000,
    "finance_unpaid_cents": 100_000,
    "finance_outstanding_invoices": 7,
    "finance_overdue_invoices": 2,
    "finance_paid_invoices_30d_cents": 200_000,
    "finance_days_sales_outstanding": 45.0,
}


def _make_connector_mock(name: str, snapshot=None, fail: bool = False):
    """Build a Mock for a connector function.

    When fail=True the mock raises, otherwise it returns *snapshot*.
    """
    m = Mock(name=f"connector_{name}")
    if fail:
        m.side_effect = RuntimeError(f"{name} connection refused")
    else:
        m.return_value = snapshot if snapshot is not None else {}
    return m


def _patch_connectors(erpnext=None, hubspot=None, quickbooks=None):
    """Context manager that patches _CONNECTORS in the orchestrator module.

    Each argument should be a Mock (or None to use a default empty-success mock).
    """
    erpnext_mock = erpnext if erpnext is not None else _make_connector_mock("erpnext", {})
    hubspot_mock = hubspot if hubspot is not None else _make_connector_mock("hubspot", {})
    qb_mock = quickbooks if quickbooks is not None else _make_connector_mock("quickbooks", {})

    return patch(
        "src.orchestration.run_startup_guardian._CONNECTORS",
        [("erpnext", erpnext_mock), ("hubspot", hubspot_mock), ("quickbooks", qb_mock)],
    )


# ---------------------------------------------------------------------------
# 1. Happy path — all connectors succeed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_happy_path_all_connectors_succeed():
    """All three connectors succeed → all assemblers called → health computed."""
    mock_erp = _make_connector_mock("erpnext", ERPNEXT_SNAPSHOT)
    mock_hs = _make_connector_mock("hubspot", HUBSPOT_SNAPSHOT)
    mock_qb = _make_connector_mock("quickbooks", QUICKBOOKS_SNAPSHOT)

    with _patch_connectors(erpnext=mock_erp, hubspot=mock_hs, quickbooks=mock_qb):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian("tenant-1")

    # All connectors called with tenant_id
    mock_erp.assert_called_once_with("tenant-1")
    mock_hs.assert_called_once_with("tenant-1")
    mock_qb.assert_called_once_with("tenant-1")

    # connectors_ok all True
    assert result["connectors_ok"] == {
        "erpnext": True,
        "hubspot": True,
        "quickbooks": True,
    }

    # Domain states populated from snapshots
    assert result["support"]["open_issues"] == 8
    assert result["execution"]["active_projects"] == 2
    assert result["team"]["active_employees"] == 10
    assert result["finance"]["outstanding_invoices"] == 7  # overridden by quickbooks
    assert result["revenue"]["total_deals_cents"] == 500_000

    # Health computed (support unresolved=3 → ATTENTION; execution overdue=1 → AT_RISK;
    # team departures=1 → ATTENTION; finance overdue=75k → WARNING)
    assert result["overall_health"] in ("good", "attention", "critical")


# ---------------------------------------------------------------------------
# 2. Partial failure — one connector fails
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_partial_failure_one_connector_fails():
    """One connector fails → remaining assemblers still called → partial data."""
    mock_erp = _make_connector_mock("erpnext", ERPNEXT_SNAPSHOT)
    mock_hs = _make_connector_mock("hubspot", fail=True)
    mock_qb = _make_connector_mock("quickbooks", QUICKBOOKS_SNAPSHOT)

    with _patch_connectors(erpnext=mock_erp, hubspot=mock_hs, quickbooks=mock_qb):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian("tenant-1")

    # HubSpot failed → connectors_ok reflects that
    assert result["connectors_ok"]["erpnext"] is True
    assert result["connectors_ok"]["hubspot"] is False
    assert result["connectors_ok"]["quickbooks"] is True

    # Revenue state should be default (no hubspot data)
    assert result["revenue"]["total_deals_cents"] == 0
    assert result["revenue"]["active_customers"] == 0

    # ERPNext + QuickBooks data still present
    assert result["support"]["open_issues"] == 8
    assert result["finance"]["outstanding_invoices"] == 7  # quickbooks override


@pytest.mark.asyncio
async def test_partial_failure_erpnext_fails():
    """ERPNext fails → support/execution/team/finance from erpnext missing → defaults."""
    mock_erp = _make_connector_mock("erpnext", fail=True)
    mock_hs = _make_connector_mock("hubspot", HUBSPOT_SNAPSHOT)
    mock_qb = _make_connector_mock("quickbooks", QUICKBOOKS_SNAPSHOT)

    with _patch_connectors(erpnext=mock_erp, hubspot=mock_hs, quickbooks=mock_qb):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian("tenant-1")

    assert result["connectors_ok"]["erpnext"] is False
    # Support/execution/team default to zero because erpnext didn't provide data
    assert result["support"]["open_issues"] == 0
    assert result["execution"]["active_projects"] == 0
    assert result["team"]["active_employees"] == 0
    # Revenue from hubspot still present
    assert result["revenue"]["active_customers"] == 12
    # Finance from quickbooks still present
    assert result["finance"]["outstanding_invoices"] == 7


# ---------------------------------------------------------------------------
# 3. All-fail — every connector raises
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_connectors_fail():
    """All connectors fail → all defaults → health=good."""
    mock_erp = _make_connector_mock("erpnext", fail=True)
    mock_hs = _make_connector_mock("hubspot", fail=True)
    mock_qb = _make_connector_mock("quickbooks", fail=True)

    with _patch_connectors(erpnext=mock_erp, hubspot=mock_hs, quickbooks=mock_qb):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian("tenant-1")

    assert result["connectors_ok"] == {
        "erpnext": False,
        "hubspot": False,
        "quickbooks": False,
    }
    # All domain states are defaults
    assert result["support"]["open_issues"] == 0
    assert result["execution"]["active_projects"] == 0
    assert result["team"]["active_employees"] == 0
    assert result["finance"]["outstanding_invoices"] == 0
    assert result["revenue"]["total_deals_cents"] == 0
    # Health defaults to GOOD (all zeros → all GOOD → overall GOOD)
    assert result["overall_health"] == "good"


# ---------------------------------------------------------------------------
# 4. _map_health() correctness
# ---------------------------------------------------------------------------

def test_map_health_known_values():
    """_map_health maps all known strings to the correct enum value."""
    from src.orchestration.run_startup_guardian import _map_health
    from src.states.schemas import SupportHealth

    assert _map_health("critical") == SupportHealth.CRITICAL
    assert _map_health("attention") == SupportHealth.ATTENTION
    assert _map_health("good") == SupportHealth.GOOD
    assert _map_health("on_track") == SupportHealth.GOOD
    assert _map_health("at_risk") == SupportHealth.ATTENTION
    assert _map_health("blocked") == SupportHealth.CRITICAL
    assert _map_health("healthy") == SupportHealth.GOOD
    assert _map_health("warning") == SupportHealth.ATTENTION


def test_map_health_unknown_defaults_to_good():
    """Unknown health string defaults to GOOD."""
    from src.orchestration.run_startup_guardian import _map_health
    from src.states.schemas import SupportHealth

    assert _map_health("unknown_value") == SupportHealth.GOOD
    assert _map_health("") == SupportHealth.GOOD
    assert _map_health("CRITICAL") == SupportHealth.GOOD  # case-sensitive


def test_map_health_enum_passthrough():
    """_map_health handles enum objects by extracting .value."""
    from src.orchestration.run_startup_guardian import _map_health
    from src.states.schemas import SupportHealth, ExecutionHealth, FinancialHealth

    # SupportHealth enum → extracted .value → mapped
    assert _map_health(SupportHealth.CRITICAL) == SupportHealth.CRITICAL
    assert _map_health(ExecutionHealth.ON_TRACK) == SupportHealth.GOOD
    assert _map_health(FinancialHealth.WARNING) == SupportHealth.ATTENTION


# ---------------------------------------------------------------------------
# 5. Health priority ordering — worst wins
# ---------------------------------------------------------------------------

def test_health_priority_ordering():
    """Worst health wins: CRITICAL > ATTENTION > GOOD in priority."""
    from src.orchestration.run_startup_guardian import _HEALTH_PRIORITY
    from src.states.schemas import SupportHealth

    # CRITICAL has lowest index → highest priority
    assert _HEALTH_PRIORITY.index(SupportHealth.CRITICAL) < _HEALTH_PRIORITY.index(SupportHealth.ATTENTION)
    assert _HEALTH_PRIORITY.index(SupportHealth.ATTENTION) < _HEALTH_PRIORITY.index(SupportHealth.GOOD)


@pytest.mark.asyncio
async def test_worst_health_wins_overall():
    """When support=GOOD but execution=BLOCKED→CRITICAL, overall should be CRITICAL."""
    erp_critical_exec = {
        "support_open_issues": 0,
        "support_unresolved_issues": 0,         # → GOOD
        "execution_active_projects": 1,
        "execution_overdue_tasks": 10,           # → BLOCKED (>3)
        "execution_milestones_total": 5,
        "execution_milestones_completed": 0,
        "execution_avg_completion": 10.0,
        "team_active_count": 5,
        "team_departments": {},
        "team_new_joinees_30d": 0,
        "team_departures_30d": 0,               # → GOOD
        "finance_total_outstanding_cents": 0,
        "finance_overdue_cents": 0,              # → HEALTHY
        "finance_unpaid_cents": 0,
        "finance_outstanding_invoices": 0,
        "finance_overdue_invoices": 0,
        "finance_paid_invoices_30d_cents": 0,
        "finance_days_sales_outstanding": None,
    }
    mock_erp = _make_connector_mock("erpnext", erp_critical_exec)

    with _patch_connectors(erpnext=mock_erp):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian("tenant-1")

    # execution blocked → maps to CRITICAL via _map_health
    assert result["overall_health"] == "critical"


# ---------------------------------------------------------------------------
# 6. Assembler call order — correct grouping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_assembler_call_order():
    """Verify data flows from correct sources:

    ERPNext raw → support, execution, team, finance
    HubSpot raw → revenue
    QuickBooks raw → finance (overrides ERPNext finance)
    """
    mock_erp = _make_connector_mock("erpnext", ERPNEXT_SNAPSHOT)
    mock_hs = _make_connector_mock("hubspot", HUBSPOT_SNAPSHOT)
    mock_qb = _make_connector_mock("quickbooks", QUICKBOOKS_SNAPSHOT)

    with _patch_connectors(erpnext=mock_erp, hubspot=mock_hs, quickbooks=mock_qb):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian("tenant-1")

    # Finance should come from QuickBooks (last to set it), not ERPNext
    assert result["finance"]["outstanding_invoices"] == 7   # QB value
    assert result["finance"]["total_outstanding_cents"] == 300_000  # QB value

    # Support/Execution/Team from ERPNext
    assert result["support"]["open_issues"] == 8  # ERPNext value
    assert result["execution"]["active_projects"] == 2  # ERPNext value
    assert result["team"]["active_employees"] == 10  # ERPNext value

    # Revenue from HubSpot
    assert result["revenue"]["active_customers"] == 12  # HubSpot value


# ---------------------------------------------------------------------------
# 7. connectors_ok accuracy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connectors_ok_all_true():
    """When all connectors succeed, connectors_ok has all True."""
    mock_erp = _make_connector_mock("erpnext", ERPNEXT_SNAPSHOT)
    mock_hs = _make_connector_mock("hubspot", HUBSPOT_SNAPSHOT)
    mock_qb = _make_connector_mock("quickbooks", QUICKBOOKS_SNAPSHOT)

    with _patch_connectors(erpnext=mock_erp, hubspot=mock_hs, quickbooks=mock_qb):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian("tenant-1")

    assert result["connectors_ok"]["erpnext"] is True
    assert result["connectors_ok"]["hubspot"] is True
    assert result["connectors_ok"]["quickbooks"] is True
    assert len(result["connectors_ok"]) == 3


@pytest.mark.asyncio
async def test_connectors_ok_mixed():
    """Two succeed, one fails → connectors_ok reflects each correctly."""
    mock_erp = _make_connector_mock("erpnext", ERPNEXT_SNAPSHOT, fail=True)
    mock_hs = _make_connector_mock("hubspot", HUBSPOT_SNAPSHOT)
    mock_qb = _make_connector_mock("quickbooks", QUICKBOOKS_SNAPSHOT, fail=True)

    with _patch_connectors(erpnext=mock_erp, hubspot=mock_hs, quickbooks=mock_qb):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian("tenant-1")

    assert result["connectors_ok"]["erpnext"] is False
    assert result["connectors_ok"]["hubspot"] is True
    assert result["connectors_ok"]["quickbooks"] is False


# ---------------------------------------------------------------------------
# 8. raw_snapshots preserved
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_raw_snapshots_contain_original_responses():
    """raw_snapshots stores the exact dict each connector returned."""
    mock_erp = _make_connector_mock("erpnext", ERPNEXT_SNAPSHOT)
    mock_hs = _make_connector_mock("hubspot", HUBSPOT_SNAPSHOT)
    mock_qb = _make_connector_mock("quickbooks", QUICKBOOKS_SNAPSHOT)

    with _patch_connectors(erpnext=mock_erp, hubspot=mock_hs, quickbooks=mock_qb):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian("tenant-1")

    # raw_snapshots keyed by connector name
    assert "erpnext" in result["raw_snapshots"]
    assert "hubspot" in result["raw_snapshots"]
    assert "quickbooks" in result["raw_snapshots"]

    # Exact snapshot content preserved
    assert result["raw_snapshots"]["erpnext"] == ERPNEXT_SNAPSHOT
    assert result["raw_snapshots"]["hubspot"] == HUBSPOT_SNAPSHOT
    assert result["raw_snapshots"]["quickbooks"] == QUICKBOOKS_SNAPSHOT


@pytest.mark.asyncio
async def test_raw_snapshots_missing_for_failed_connector():
    """Failed connector has no entry in raw_snapshots."""
    mock_erp = _make_connector_mock("erpnext", ERPNEXT_SNAPSHOT)
    mock_hs = _make_connector_mock("hubspot", fail=True)
    mock_qb = _make_connector_mock("quickbooks", QUICKBOOKS_SNAPSHOT)

    with _patch_connectors(erpnext=mock_erp, hubspot=mock_hs, quickbooks=mock_qb):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian("tenant-1")

    assert "erpnext" in result["raw_snapshots"]
    assert "hubspot" not in result["raw_snapshots"]
    assert "quickbooks" in result["raw_snapshots"]


# ---------------------------------------------------------------------------
# 9. run_id uniqueness
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_id_unique_per_invocation():
    """Each invocation of run_startup_guardian produces a unique run_id."""
    run_ids = set()
    for _ in range(5):
        mock_erp = _make_connector_mock("erpnext", ERPNEXT_SNAPSHOT)
        mock_hs = _make_connector_mock("hubspot", HUBSPOT_SNAPSHOT)
        mock_qb = _make_connector_mock("quickbooks", QUICKBOOKS_SNAPSHOT)

        with _patch_connectors(erpnext=mock_erp, hubspot=mock_hs, quickbooks=mock_qb):
            from src.orchestration.run_startup_guardian import run_startup_guardian
            result = await run_startup_guardian("tenant-1")
            run_ids.add(result["run_id"])

    assert len(run_ids) == 5, f"Expected 5 unique run_ids, got {len(run_ids)}"


# ---------------------------------------------------------------------------
# 10. tenant_id propagation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tenant_id_flows_through_pipeline():
    """The tenant_id passed to run_startup_guardian appears in the result."""
    mock_erp = _make_connector_mock("erpnext", ERPNEXT_SNAPSHOT)
    mock_hs = _make_connector_mock("hubspot", HUBSPOT_SNAPSHOT)
    mock_qb = _make_connector_mock("quickbooks", QUICKBOOKS_SNAPSHOT)

    test_tenant = "my-special-startup-xyz"
    with _patch_connectors(erpnext=mock_erp, hubspot=mock_hs, quickbooks=mock_qb):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian(test_tenant)

    assert result["tenant_id"] == test_tenant

    # tenant_id also forwarded to each connector
    mock_erp.assert_called_once_with(test_tenant)
    mock_hs.assert_called_once_with(test_tenant)
    mock_qb.assert_called_once_with(test_tenant)


@pytest.mark.asyncio
async def test_tenant_id_not_corrupted():
    """tenant_id survives the full round-trip without mutation."""
    mock_erp = _make_connector_mock("erpnext", ERPNEXT_SNAPSHOT)
    mock_hs = _make_connector_mock("hubspot", HUBSPOT_SNAPSHOT)
    mock_qb = _make_connector_mock("quickbooks", QUICKBOOKS_SNAPSHOT)

    original_tenant = "tenant_with_underscores-123"
    with _patch_connectors(erpnext=mock_erp, hubspot=mock_hs, quickbooks=mock_qb):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian(original_tenant)

    assert result["tenant_id"] == original_tenant
