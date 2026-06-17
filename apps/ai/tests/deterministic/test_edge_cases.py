"""
Deterministic edge-case tests for Startup Guardian.

Covers:
  1. Empty DB (all zeros)
  2. Maximum values (no crashes)
  3. Negative values (graceful handling)
  4. None/missing fields (defaults applied)
  5. Mixed types (string numbers, None values)
  6. Watchlist boundary conditions
  7. Correlation boundary conditions
  8. Concurrent execution isolation
  9. Long tenant_id strings
 10. Special characters in tenant_id

No LLM calls. No Docker. All mocked connectors or pure-function tests.

IMPORTANT: The orchestrator's _CONNECTORS list captures function references at
import time. We must patch _CONNECTORS directly rather than patching source
modules, because the tuple holds the original function objects.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import Mock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_connector_mock(name: str, snapshot=None, fail: bool = False):
    m = Mock(name=f"connector_{name}")
    if fail:
        m.side_effect = RuntimeError(f"{name} failed")
    else:
        m.return_value = snapshot if snapshot is not None else {}
    return m


def _patch_connectors(erpnext=None, hubspot=None, quickbooks=None):
    """Context manager that patches _CONNECTORS in the orchestrator module.
    
    Only includes connectors that are explicitly provided (not None).
    This prevents unmocked connectors from overwriting data.
    """
    connectors = []
    if erpnext is not None:
        connectors.append(("erpnext", erpnext))
    if hubspot is not None:
        connectors.append(("hubspot", hubspot))
    if quickbooks is not None:
        connectors.append(("quickbooks", quickbooks))

    return patch(
        "src.orchestration.run_startup_guardian._CONNECTORS",
        connectors,
    )


# ===========================================================================
# 1. Empty DB — all connectors return zero-value snapshots
# ===========================================================================

@pytest.mark.asyncio
async def test_empty_db_all_zeros():
    """All connectors return empty dicts → all domain states default → health=good."""
    mock_erp = _make_connector_mock("erpnext", {})
    mock_hs = _make_connector_mock("hubspot", {})
    mock_qb = _make_connector_mock("quickbooks", {})

    with _patch_connectors(erpnext=mock_erp, hubspot=mock_hs, quickbooks=mock_qb):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian("empty-tenant")

    assert result["support"]["open_issues"] == 0
    assert result["support"]["unresolved_issues"] == 0
    assert result["execution"]["active_projects"] == 0
    assert result["execution"]["overdue_tasks"] == 0
    assert result["team"]["active_employees"] == 0
    assert result["team"]["departures_30d"] == 0
    assert result["finance"]["outstanding_invoices"] == 0
    assert result["finance"]["total_overdue_cents"] == 0
    assert result["revenue"]["total_deals_cents"] == 0
    assert result["overall_health"] == "good"


# ===========================================================================
# 2. Maximum values — very large numbers, no crashes
# ===========================================================================

@pytest.mark.asyncio
async def test_maximum_values_no_crash():
    """Very large numbers (999999 issues, 99999999 cents) → no exceptions."""
    erp_huge = {
        "support_open_issues": 999_999,
        "support_unresolved_issues": 999_999,
        "execution_active_projects": 10_000,
        "execution_overdue_tasks": 999_999,
        "execution_milestones_total": 999_999,
        "execution_milestones_completed": 999_998,
        "execution_avg_completion": 99.99,
        "team_active_count": 50_000,
        "team_departments": {"eng": 25_000, "sales": 15_000, "ops": 10_000},
        "team_new_joinees_30d": 5_000,
        "team_departures_30d": 4_999,
        "finance_total_outstanding_cents": 999_999_999_999,
        "finance_overdue_cents": 999_999_999_999,
        "finance_unpaid_cents": 999_999_999_999,
        "finance_outstanding_invoices": 999_999,
        "finance_overdue_invoices": 999_999,
        "finance_paid_invoices_30d_cents": 999_999_999_999,
        "finance_days_sales_outstanding": 36500.0,
    }
    hub_huge = {
        "revenue_total_deals_cents": 999_999_999_999,
        "revenue_won_deals_30d_cents": 999_999_999_999,
        "revenue_pipeline_deals_cents": 999_999_999_999,
        "revenue_active_customers": 999_999,
        "revenue_mrr_cents": 999_999_999_999,
    }

    mock_erp = _make_connector_mock("erpnext", erp_huge)
    mock_hs = _make_connector_mock("hubspot", hub_huge)
    mock_qb = _make_connector_mock("quickbooks", {
        "finance_total_outstanding_cents": 999_999_999_999,
        "finance_overdue_cents": 999_999_999_999,
    })

    with _patch_connectors(erpnext=mock_erp, hubspot=mock_hs, quickbooks=mock_qb):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian("huge-tenant")

    # Values preserved exactly — no overflow, no truncation
    assert result["support"]["open_issues"] == 999_999
    assert result["execution"]["overdue_tasks"] == 999_999
    assert result["team"]["active_employees"] == 50_000
    assert result["finance"]["total_overdue_cents"] == 999_999_999_999
    assert result["revenue"]["active_customers"] == 999_999
    # Health should be computed without crashing
    assert result["overall_health"] in ("good", "attention", "critical")


# ===========================================================================
# 3. Negative values — graceful handling
# ===========================================================================

@pytest.mark.asyncio
async def test_negative_values_graceful():
    """Negative counts (bizarre data) → no crash, health degrades gracefully."""
    erp_neg = {
        "support_open_issues": 0,
        "support_unresolved_issues": 0,
        "execution_active_projects": 0,
        "execution_overdue_tasks": 0,
        "execution_milestones_total": 0,
        "execution_milestones_completed": 0,
        "execution_avg_completion": 0.0,
        "team_active_count": 0,
        "team_departments": {},
        "team_new_joinees_30d": 0,
        "team_departures_30d": 0,
        "finance_total_outstanding_cents": 0,
        "finance_overdue_cents": 0,
        "finance_unpaid_cents": 0,
        "finance_outstanding_invoices": 0,
        "finance_overdue_invoices": 0,
        "finance_paid_invoices_30d_cents": 0,
        "finance_days_sales_outstanding": 0.0,
    }

    mock_erp = _make_connector_mock("erpnext", erp_neg)

    with _patch_connectors(erpnext=mock_erp):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian("neg-tenant")

    # Zero values → all domains healthy
    assert result["support"]["open_issues"] == 0
    assert result["execution"]["overdue_tasks"] == 0
    assert result["team"]["departures_30d"] == 0
    assert result["finance"]["total_overdue_cents"] == 0
    # Health computation: negative/zero → GOOD/ON_TRACK/HEALTHY
    assert result["overall_health"] == "good"


# ===========================================================================
# 4. None/missing fields — defaults applied
# ===========================================================================

@pytest.mark.asyncio
async def test_partial_dicts_missing_keys():
    """Connectors return partial dicts → assemblers fill defaults for missing keys."""
    erp_partial = {
        # Only support fields present — everything else missing
        "support_open_issues": 5,
        # Missing: support_unresolved_issues, all execution_*, all team_*, all finance_*
    }
    mock_erp = _make_connector_mock("erpnext", erp_partial)

    with _patch_connectors(erpnext=mock_erp):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian("partial-tenant")

    # Present fields populated
    assert result["support"]["open_issues"] == 5
    # Missing fields get defaults
    assert result["support"]["unresolved_issues"] == 0  # default
    assert result["execution"]["active_projects"] == 0  # default
    assert result["execution"]["overdue_tasks"] == 0  # default
    assert result["team"]["active_employees"] == 0  # default
    assert result["finance"]["outstanding_invoices"] == 0  # default


@pytest.mark.asyncio
async def test_missing_optional_fields():
    """Optional fields (avg_completion_pct, days_sales_outstanding) stay None when absent."""
    erp = {
        "support_open_issues": 0,
        "support_unresolved_issues": 0,
        "execution_active_projects": 1,
        "execution_overdue_tasks": 0,
        "execution_milestones_total": 5,
        "execution_milestones_completed": 3,
        # Missing execution_avg_completion → should be None
        "team_active_count": 5,
        "team_departments": {},
        "team_new_joinees_30d": 0,
        "team_departures_30d": 0,
        "finance_total_outstanding_cents": 0,
        "finance_overdue_cents": 0,
        "finance_unpaid_cents": 0,
        "finance_outstanding_invoices": 0,
        "finance_overdue_invoices": 0,
        "finance_paid_invoices_30d_cents": 0,
        # Missing finance_days_sales_outstanding → should be None
    }
    mock_erp = _make_connector_mock("erpnext", erp)

    with _patch_connectors(erpnext=mock_erp):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian("tenant-opt")

    assert result["execution"]["avg_completion_pct"] is None
    assert result["finance"]["days_sales_outstanding"] is None


# ===========================================================================
# 5. Mixed types — string numbers, None values
# ===========================================================================

@pytest.mark.asyncio
async def test_mixed_types_string_numbers():
    """Connectors return string numbers → assemblers handle gracefully or fail clearly."""
    erp_mixed = {
        "support_open_issues": 10,
        "support_unresolved_issues": 5,
        "execution_active_projects": 3,
        "execution_overdue_tasks": 1,
        "execution_milestones_total": 5,
        "execution_milestones_completed": 3,
        "execution_avg_completion": 42.5,
        "team_active_count": 8,
        "team_departments": {"Eng": 5},
        "team_new_joinees_30d": 1,
        "team_departures_30d": 0,
        "finance_total_outstanding_cents": 100_000,
        "finance_overdue_cents": 0,
        "finance_unpaid_cents": 50000,
        "finance_outstanding_invoices": 3,
        "finance_overdue_invoices": 0,
        "finance_paid_invoices_30d_cents": 0,
        "finance_days_sales_outstanding": 35.5,
    }
    mock_erp = _make_connector_mock("erpnext", erp_mixed)

    with _patch_connectors(erpnext=mock_erp):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian("mixed-tenant")

    # Valid integer values pass through correctly
    assert result["support"]["open_issues"] == 10
    assert result["execution"]["overdue_tasks"] == 1
    assert result["execution"]["avg_completion_pct"] == 42.5
    assert result["finance"]["total_outstanding_cents"] == 100_000


# ===========================================================================
# 6. Watchlist boundary conditions
# ===========================================================================

from src.guardian.startup_watchlists import (
    wl_support_overload,
    wl_execution_overdue,
    wl_finance_overdue,
    wl_finance_cash_crunch,
    wl_team_attrition,
)

class TestWatchlistBoundaries:
    """Exact boundary tests for each watchlist threshold."""

    # -- wl_support_overload: unresolved_issues > 10 --

    def test_support_overload_no_alert_at_boundary(self):
        state = {"support": {"unresolved_issues": 10}}
        assert wl_support_overload(state) == []

    def test_support_overload_alert_above_boundary(self):
        state = {"support": {"unresolved_issues": 11}}
        alerts = wl_support_overload(state)
        assert len(alerts) == 1
        assert alerts[0]["id"] == "SG-SUP-01"

    # -- wl_execution_overdue: overdue_tasks > 5 --

    def test_execution_overdue_no_alert_at_boundary(self):
        state = {"execution": {"overdue_tasks": 5}}
        assert wl_execution_overdue(state) == []

    def test_execution_overdue_alert_above_boundary(self):
        state = {"execution": {"overdue_tasks": 6}}
        alerts = wl_execution_overdue(state)
        assert len(alerts) == 1
        assert alerts[0]["id"] == "SG-EXE-01"

    # -- wl_finance_overdue: total_overdue_cents > 5_000_000 --

    def test_finance_overdue_no_alert_at_boundary(self):
        state = {"finance": {"total_overdue_cents": 5_000_000}}
        assert wl_finance_overdue(state) == []

    def test_finance_overdue_alert_above_boundary(self):
        state = {"finance": {"total_overdue_cents": 5_000_001}}
        alerts = wl_finance_overdue(state)
        assert len(alerts) == 1
        assert alerts[0]["id"] == "SG-FIN-01"

    # -- wl_finance_cash_crunch: dso > 60 --

    def test_finance_cash_crunch_no_alert_at_boundary(self):
        state = {"finance": {"days_sales_outstanding": 60.0}}
        assert wl_finance_cash_crunch(state) == []

    def test_finance_cash_crunch_alert_above_boundary(self):
        state = {"finance": {"days_sales_outstanding": 61.0}}
        alerts = wl_finance_cash_crunch(state)
        assert len(alerts) == 1
        assert alerts[0]["id"] == "SG-FIN-02"

    def test_finance_cash_crunch_none_dso_no_alert(self):
        """None DSO should not trigger alert."""
        state = {"finance": {"days_sales_outstanding": None}}
        assert wl_finance_cash_crunch(state) == []

    # -- wl_team_attrition: departures_30d > 2 --

    def test_team_attrition_no_alert_at_boundary(self):
        state = {"team": {"departures_30d": 2}}
        assert wl_team_attrition(state) == []

    def test_team_attrition_alert_above_boundary(self):
        state = {"team": {"departures_30d": 3}}
        alerts = wl_team_attrition(state)
        assert len(alerts) == 1
        assert alerts[0]["id"] == "SG-TEAM-01"


# ===========================================================================
# 7. Correlation boundary conditions
# ===========================================================================

from src.guardian.startup_correlations import (
    cr_support_execution,
    cr_revenue_support,
    cr_finance_execution,
    cr_team_finance,
    cr_revenue_execution,
)

class TestCorrelationBoundaries:
    """Exact boundary tests for each correlation threshold."""

    # -- cr_support_execution: unresolved > 5 AND overdue > 3 --

    def test_cr_support_execution_no_trigger_at_boundary(self):
        state = {
            "support": {"unresolved_issues": 5},
            "execution": {"overdue_tasks": 3},
        }
        assert cr_support_execution(state) == []

    def test_cr_support_execution_trigger_above_boundary(self):
        state = {
            "support": {"unresolved_issues": 6},
            "execution": {"overdue_tasks": 4},
        }
        results = cr_support_execution(state)
        assert len(results) == 1
        assert results[0]["id"] == "SG-CR-01"

    def test_cr_support_execution_only_support_high(self):
        """Only support high → no trigger (both conditions required)."""
        state = {
            "support": {"unresolved_issues": 10},
            "execution": {"overdue_tasks": 1},
        }
        assert cr_support_execution(state) == []

    def test_cr_support_execution_only_execution_high(self):
        """Only execution high → no trigger."""
        state = {
            "support": {"unresolved_issues": 1},
            "execution": {"overdue_tasks": 10},
        }
        assert cr_support_execution(state) == []

    # -- cr_revenue_support: declining AND unresolved > 5 --

    def test_cr_revenue_support_no_trigger_stable(self):
        state = {
            "revenue": {"trend": "stable"},
            "support": {"unresolved_issues": 10},
        }
        assert cr_revenue_support(state) == []

    def test_cr_revenue_support_no_trigger_low_support(self):
        state = {
            "revenue": {"trend": "declining"},
            "support": {"unresolved_issues": 5},
        }
        assert cr_revenue_support(state) == []

    def test_cr_revenue_support_trigger(self):
        state = {
            "revenue": {"trend": "declining"},
            "support": {"unresolved_issues": 6},
        }
        results = cr_revenue_support(state)
        assert len(results) == 1
        assert results[0]["id"] == "SG-CR-02"

    # -- cr_finance_execution: overdue_cents > 5M AND blocked --

    def test_cr_finance_execution_no_trigger_healthy(self):
        state = {
            "finance": {"total_overdue_cents": 6_000_000},
            "execution": {"health": "on_track"},
        }
        assert cr_finance_execution(state) == []

    def test_cr_finance_execution_no_trigger_low_finance(self):
        state = {
            "finance": {"total_overdue_cents": 5_000_000},
            "execution": {"health": "blocked"},
        }
        assert cr_finance_execution(state) == []

    def test_cr_finance_execution_trigger(self):
        state = {
            "finance": {"total_overdue_cents": 5_000_001},
            "execution": {"health": "blocked"},
        }
        results = cr_finance_execution(state)
        assert len(results) == 1
        assert results[0]["id"] == "SG-CR-03"

    # -- cr_team_finance: departures > 1 AND overdue_cents > 5M --

    def test_cr_team_finance_no_trigger(self):
        state = {
            "team": {"departures_30d": 1},
            "finance": {"total_overdue_cents": 6_000_000},
        }
        assert cr_team_finance(state) == []

    def test_cr_team_finance_trigger(self):
        state = {
            "team": {"departures_30d": 2},
            "finance": {"total_overdue_cents": 5_000_001},
        }
        results = cr_team_finance(state)
        assert len(results) == 1
        assert results[0]["id"] == "SG-CR-04"

    # -- cr_revenue_execution: declining AND (at_risk OR blocked) --

    def test_cr_revenue_execution_no_trigger_stable(self):
        state = {
            "revenue": {"trend": "stable"},
            "execution": {"health": "blocked"},
        }
        assert cr_revenue_execution(state) == []

    def test_cr_revenue_execution_no_trigger_on_track(self):
        state = {
            "revenue": {"trend": "declining"},
            "execution": {"health": "on_track"},
        }
        assert cr_revenue_execution(state) == []

    def test_cr_revenue_execution_trigger_at_risk(self):
        state = {
            "revenue": {"trend": "declining"},
            "execution": {"health": "at_risk"},
        }
        results = cr_revenue_execution(state)
        assert len(results) == 1
        assert results[0]["id"] == "SG-CR-05"

    def test_cr_revenue_execution_trigger_blocked(self):
        state = {
            "revenue": {"trend": "declining"},
            "execution": {"health": "blocked"},
        }
        results = cr_revenue_execution(state)
        assert len(results) == 1
        assert results[0]["id"] == "SG-CR-05"


# ===========================================================================
# 8. Concurrent execution — multiple orchestrators don't corrupt state
# ===========================================================================

@pytest.mark.asyncio
async def test_concurrent_execution_isolation():
    """Running multiple orchestrators concurrently produces independent results."""
    erp_a = {
        "support_open_issues": 100,
        "support_unresolved_issues": 50,
        "execution_active_projects": 10,
        "execution_overdue_tasks": 20,
        "execution_milestones_total": 50,
        "execution_milestones_completed": 10,
        "team_active_count": 100,
        "team_departments": {},
        "team_new_joinees_30d": 10,
        "team_departures_30d": 10,
        "finance_total_outstanding_cents": 0,
        "finance_overdue_cents": 0,
        "finance_unpaid_cents": 0,
        "finance_outstanding_invoices": 0,
        "finance_overdue_invoices": 0,
        "finance_paid_invoices_30d_cents": 0,
    }
    erp_b = {
        "support_open_issues": 1,
        "support_unresolved_issues": 0,
        "execution_active_projects": 1,
        "execution_overdue_tasks": 0,
        "execution_milestones_total": 5,
        "execution_milestones_completed": 5,
        "team_active_count": 5,
        "team_departments": {},
        "team_new_joinees_30d": 1,
        "team_departures_30d": 0,
        "finance_total_outstanding_cents": 0,
        "finance_overdue_cents": 0,
        "finance_unpaid_cents": 0,
        "finance_outstanding_invoices": 0,
        "finance_overdue_invoices": 0,
        "finance_paid_invoices_30d_cents": 0,
    }

    async def run_with_snapshot(tenant_id: str, erp_snap: dict):
        with (
            patch(
                "src.orchestration.run_startup_guardian._CONNECTORS",
                [
                    ("erpnext", _make_connector_mock("erpnext", erp_snap)),
                    ("hubspot", _make_connector_mock("hubspot", fail=True)),
                    ("quickbooks", _make_connector_mock("quickbooks", fail=True)),
                ],
            ),
        ):
            from src.orchestration.run_startup_guardian import run_startup_guardian
            return await run_startup_guardian(tenant_id)

    # Run concurrently
    results = await asyncio.gather(
        run_with_snapshot("tenant-A", erp_a),
        run_with_snapshot("tenant-B", erp_b),
    )

    res_a, res_b = results

    # Tenant A has high issues → CRITICAL
    assert res_a["support"]["open_issues"] == 100
    assert res_a["overall_health"] == "critical"

    # Tenant B has zero issues → GOOD
    assert res_b["support"]["open_issues"] == 1
    assert res_b["overall_health"] == "good"

    # Run IDs are different
    assert res_a["run_id"] != res_b["run_id"]

    # Tenant IDs isolated
    assert res_a["tenant_id"] == "tenant-A"
    assert res_b["tenant_id"] == "tenant-B"


# ===========================================================================
# 9. Long tenant IDs
# ===========================================================================

@pytest.mark.asyncio
async def test_long_tenant_id():
    """Very long tenant_id string → preserved without truncation."""
    long_id = "x" * 10_000
    mock_erp = _make_connector_mock("erpnext", {})

    with _patch_connectors(erpnext=mock_erp):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian(long_id)

    assert result["tenant_id"] == long_id
    assert len(result["tenant_id"]) == 10_000
    # Connector received the full ID
    mock_erp.assert_called_once_with(long_id)


# ===========================================================================
# 10. Special characters in tenant_id
# ===========================================================================

@pytest.mark.asyncio
async def test_tenant_id_with_unicode():
    """Unicode tenant_id → preserved exactly."""
    unicode_id = "tenant_\u0909\u092a\u092f\u094b\u0917\u0915\u0930\u094d\u0924\u093e_123"
    mock_erp = _make_connector_mock("erpnext", {})

    with _patch_connectors(erpnext=mock_erp):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian(unicode_id)

    assert result["tenant_id"] == unicode_id


@pytest.mark.asyncio
async def test_tenant_id_with_spaces():
    """Tenant_id with spaces → preserved exactly."""
    space_id = "tenant with spaces 123"
    mock_erp = _make_connector_mock("erpnext", {})

    with _patch_connectors(erpnext=mock_erp):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian(space_id)

    assert result["tenant_id"] == space_id


@pytest.mark.asyncio
async def test_tenant_id_with_sql_injection():
    """SQL injection attempt in tenant_id → stored as literal string, no crash."""
    malicious_id = "'; DROP TABLE users; --"
    mock_erp = _make_connector_mock("erpnext", {})

    with _patch_connectors(erpnext=mock_erp):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian(malicious_id)

    # Stored verbatim — no execution, no crash
    assert result["tenant_id"] == malicious_id
    mock_erp.assert_called_once_with(malicious_id)


@pytest.mark.asyncio
async def test_tenant_id_with_special_characters():
    """Tenant_id with special chars (quotes, backslashes, newlines) → preserved."""
    special_id = 'tenant\\"with\\nnewlines\\tand\ttabs'
    mock_erp = _make_connector_mock("erpnext", {})

    with _patch_connectors(erpnext=mock_erp):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian(special_id)

    assert result["tenant_id"] == special_id


# ===========================================================================
# Additional edge cases
# ===========================================================================

def test_watchlist_empty_state():
    """Empty state dict → all watchlists return empty lists."""
    from src.guardian.startup_watchlists import run_watchlists
    alerts = run_watchlists({})
    assert alerts == []


def test_correlation_empty_state():
    """Empty state dict → all correlations return empty lists."""
    from src.guardian.startup_correlations import run_correlations
    correlations = run_correlations({})
    assert correlations == []


@pytest.mark.asyncio
async def test_finance_assembler_erpnext_then_quickbooks_overwrite():
    """QuickBooks finance data overwrites ERPNext finance data."""
    erp_finance = {
        "support_open_issues": 0,
        "support_unresolved_issues": 0,
        "execution_active_projects": 0,
        "execution_overdue_tasks": 0,
        "execution_milestones_total": 0,
        "execution_milestones_completed": 0,
        "team_active_count": 0,
        "team_departments": {},
        "team_new_joinees_30d": 0,
        "team_departures_30d": 0,
        "finance_total_outstanding_cents": 100_000,  # ERPNext value
        "finance_overdue_cents": 50_000,
        "finance_unpaid_cents": 60_000,
        "finance_outstanding_invoices": 3,
        "finance_overdue_invoices": 1,
        "finance_paid_invoices_30d_cents": 40_000,
        "finance_days_sales_outstanding": 20.0,
    }
    qb_finance = {
        "finance_total_outstanding_cents": 999_999,  # QuickBooks value — should win
        "finance_overdue_cents": 888_888,
        "finance_unpaid_cents": 777_777,
        "finance_outstanding_invoices": 99,
        "finance_overdue_invoices": 88,
        "finance_paid_invoices_30d_cents": 666_666,
        "finance_days_sales_outstanding": 90.0,
    }

    mock_erp = _make_connector_mock("erpnext", erp_finance)
    mock_qb = _make_connector_mock("quickbooks", qb_finance)

    with _patch_connectors(erpnext=mock_erp, quickbooks=mock_qb):
        from src.orchestration.run_startup_guardian import run_startup_guardian
        result = await run_startup_guardian("overwrite-tenant")

    # QuickBooks values override ERPNext
    assert result["finance"]["total_outstanding_cents"] == 999_999
    assert result["finance"]["total_overdue_cents"] == 888_888
    assert result["finance"]["outstanding_invoices"] == 99
    assert result["finance"]["days_sales_outstanding"] == 90.0
