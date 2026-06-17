"""Deterministic test fixtures — no LLM, no network, no Docker.

Fixtures for the deterministic test suite. Every fixture is pure,
synchronous, and produces deterministic output.  No external services
are contacted.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure src is importable (matches root conftest.py path setup)
# ---------------------------------------------------------------------------
_AI_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC_ROOT = _AI_ROOT / "src"
_REPO_ROOT = _AI_ROOT.parent.parent

for p in [str(_REPO_ROOT), str(_AI_ROOT), str(_SRC_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)


# ===========================================================================
# Healthy State Snapshots
# ===========================================================================

@pytest.fixture
def healthy_erpnext_snapshot() -> Dict[str, Any]:
    """ERPNext snapshot representing a healthy startup."""
    return {
        "support_open_issues": 3,
        "support_unresolved_issues": 2,
        "support_open_priority_issues": 0,
        "execution_active_projects": 4,
        "execution_overdue_tasks": 1,
        "execution_milestones_total": 10,
        "execution_milestones_completed": 7,
        "execution_avg_completion": 70.0,
        "team_active_count": 15,
        "team_departments": {"Engineering": 8, "Product": 3, "Design": 2, "Marketing": 2},
        "team_new_joinees_30d": 2,
        "finance_unpaid_cents": 500000,
        "finance_overdue_cents": 100000,
        "finance_total_outstanding_cents": 600000,
    }


@pytest.fixture
def healthy_hubspot_snapshot() -> Dict[str, Any]:
    """HubSpot snapshot representing a healthy startup."""
    return {
        "revenue_total_deals_cents": 100000000,
        "revenue_won_deals_30d_cents": 50000000,
        "revenue_pipeline_deals_cents": 50000000,
        "revenue_active_customers": 5,
        "revenue_mrr_cents": None,
    }


@pytest.fixture
def healthy_quickbooks_snapshot() -> Dict[str, Any]:
    """QuickBooks snapshot representing a healthy startup."""
    return {
        "finance_outstanding_invoices": 2,
        "finance_total_outstanding_cents": 600000,
        "finance_overdue_invoices": 0,
        "finance_total_overdue_cents": 0,
        "finance_paid_invoices_30d_cents": 2000000,
        "finance_unpaid_invoices_30d_cents": 600000,
        "finance_days_sales_outstanding": 9.0,
    }


# ===========================================================================
# Critical State Snapshots
# ===========================================================================

@pytest.fixture
def critical_erpnext_snapshot() -> Dict[str, Any]:
    """ERPNext snapshot representing a startup in critical health."""
    return {
        "support_open_issues": 25,
        "support_unresolved_issues": 20,
        "support_open_priority_issues": 8,
        "execution_active_projects": 6,
        "execution_overdue_tasks": 12,
        "execution_milestones_total": 20,
        "execution_milestones_completed": 5,
        "execution_avg_completion": 25.0,
        "team_active_count": 10,
        "team_departments": {"Engineering": 5, "Product": 2, "Design": 1, "Marketing": 2},
        "team_new_joinees_30d": 0,
        "finance_unpaid_cents": 5000000,
        "finance_overdue_cents": 3000000,
        "finance_total_outstanding_cents": 8000000,
    }


# ===========================================================================
# Mock Connector Fixtures (happy path)
# ===========================================================================

@pytest.fixture
def mock_erpnext(healthy_erpnext_snapshot: Dict[str, Any]) -> MagicMock:
    """Mock ERPNext connector returning healthy snapshot."""
    with patch("src.orchestration.run_startup_guardian.get_erpnext_snapshot") as mock:
        mock.return_value = healthy_erpnext_snapshot
        yield mock


@pytest.fixture
def mock_hubspot(healthy_hubspot_snapshot: Dict[str, Any]) -> MagicMock:
    """Mock HubSpot connector returning healthy snapshot."""
    with patch("src.orchestration.run_startup_guardian.get_hubspot_snapshot") as mock:
        mock.return_value = healthy_hubspot_snapshot
        yield mock


@pytest.fixture
def mock_quickbooks(healthy_quickbooks_snapshot: Dict[str, Any]) -> MagicMock:
    """Mock QuickBooks connector returning healthy snapshot."""
    with patch("src.orchestration.run_startup_guardian.get_quickbooks_snapshot") as mock:
        mock.return_value = healthy_quickbooks_snapshot
        yield mock


# ===========================================================================
# Failing Connector Fixtures
# ===========================================================================

@pytest.fixture
def failing_erpnext() -> MagicMock:
    """Mock ERPNext connector that raises an exception."""
    with patch("src.orchestration.run_startup_guardian.get_erpnext_snapshot") as mock:
        mock.side_effect = Exception("ERPNext connection refused")
        yield mock


@pytest.fixture
def failing_hubspot() -> MagicMock:
    """Mock HubSpot connector that raises an exception."""
    with patch("src.orchestration.run_startup_guardian.get_hubspot_snapshot") as mock:
        mock.side_effect = Exception("HubSpot API rate limited")
        yield mock


@pytest.fixture
def failing_quickbooks() -> MagicMock:
    """Mock QuickBooks connector that raises an exception."""
    with patch("src.orchestration.run_startup_guardian.get_quickbooks_snapshot") as mock:
        mock.side_effect = Exception("QuickBooks auth expired")
        yield mock


# ===========================================================================
# Call Order Tracker
# ===========================================================================

@pytest.fixture
def call_tracker() -> tuple[List[str], Any]:
    """Track the order of function calls for trajectory verification.

    Returns (calls_list, track_fn) where track_fn(name) appends to the list.
    """
    calls: List[str] = []

    def track(name: str) -> MagicMock:
        calls.append(name)
        return MagicMock()

    return calls, track


# ===========================================================================
# Edge-Case Snapshots
# ===========================================================================

@pytest.fixture
def empty_snapshot() -> Dict[str, Any]:
    """Completely empty snapshot — all keys missing."""
    return {}


@pytest.fixture
def zero_snapshot() -> Dict[str, Any]:
    """Snapshot with all numeric fields set to zero."""
    return {
        "support_open_issues": 0,
        "support_unresolved_issues": 0,
        "support_open_priority_issues": 0,
        "execution_active_projects": 0,
        "execution_overdue_tasks": 0,
        "execution_milestones_total": 0,
        "execution_milestones_completed": 0,
        "execution_avg_completion": 0.0,
        "team_active_count": 0,
        "team_departments": {},
        "team_new_joinees_30d": 0,
        "finance_unpaid_cents": 0,
        "finance_overdue_cents": 0,
        "finance_total_outstanding_cents": 0,
        "revenue_total_deals_cents": 0,
        "revenue_won_deals_30d_cents": 0,
        "revenue_pipeline_deals_cents": 0,
        "revenue_active_customers": 0,
        "revenue_mrr_cents": None,
    }


@pytest.fixture
def extreme_snapshot() -> Dict[str, Any]:
    """Snapshot with extreme (but valid) values."""
    return {
        "support_open_issues": 999999,
        "support_unresolved_issues": 999999,
        "support_open_priority_issues": 999999,
        "execution_active_projects": 1000,
        "execution_overdue_tasks": 500,
        "execution_milestones_total": 100000,
        "execution_milestones_completed": 50000,
        "execution_avg_completion": 99.99,
        "team_active_count": 10000,
        "team_departments": {"A": 9999},
        "team_new_joinees_30d": 5000,
        "finance_unpaid_cents": 2**53 - 1,
        "finance_overdue_cents": 2**53 - 1,
        "finance_total_outstanding_cents": 2**53 - 1,
        "revenue_total_deals_cents": 2**53 - 1,
        "revenue_won_deals_30d_cents": 2**53 - 1,
        "revenue_pipeline_deals_cents": 2**53 - 1,
        "revenue_active_customers": 100000,
        "revenue_mrr_cents": 2**53 - 1,
    }


# ===========================================================================
# Full State Dict Fixtures (for watchlist / correlation tests)
# ===========================================================================

@pytest.fixture
def healthy_state_dict() -> Dict[str, Any]:
    """Full MissionStateV2-compatible dict representing healthy state."""
    return {
        "tenant_id": "test-healthy",
        "run_id": "run-healthy-001",
        "support": {"open_issues": 3, "unresolved_issues": 2, "sla_breach_count": 0, "health": "good"},
        "execution": {"active_projects": 4, "overdue_tasks": 1, "open_tasks": 10, "completed_tasks_30d": 7, "avg_completion_pct": 70.0, "health": "on_track"},
        "team": {"active_employees": 15, "headcount_by_department": {"Engineering": 8}, "new_hires_30d": 2, "departures_30d": 0, "health": "good"},
        "finance": {"outstanding_invoices": 2, "total_outstanding_cents": 600000, "overdue_invoices": 0, "total_overdue_cents": 0, "unpaid_invoices_30d_cents": 600000, "paid_invoices_30d_cents": 2000000, "days_sales_outstanding": 9.0, "health": "healthy"},
        "revenue": {"total_deals_cents": 100000000, "won_deals_30d_cents": 50000000, "pipeline_deals_cents": 50000000, "active_customers": 5, "mrr_cents": None, "trend": "stable"},
        "overall_health": "good",
        "alert_count": 0,
        "correlation_count": 0,
        "connectors_ok": {"erpnext": True, "hubspot": True, "quickbooks": True},
        "raw_snapshots": {},
    }


@pytest.fixture
def critical_state_dict() -> Dict[str, Any]:
    """Full MissionStateV2-compatible dict representing critical state."""
    return {
        "tenant_id": "test-critical",
        "run_id": "run-critical-001",
        "support": {"open_issues": 25, "unresolved_issues": 20, "sla_breach_count": 5, "health": "critical"},
        "execution": {"active_projects": 6, "overdue_tasks": 12, "open_tasks": 20, "completed_tasks_30d": 5, "avg_completion_pct": 25.0, "health": "blocked"},
        "team": {"active_employees": 10, "headcount_by_department": {"Engineering": 5}, "new_hires_30d": 0, "departures_30d": 5, "health": "critical"},
        "finance": {"outstanding_invoices": 20, "total_outstanding_cents": 8000000, "overdue_invoices": 10, "total_overdue_cents": 3000000, "unpaid_invoices_30d_cents": 8000000, "paid_invoices_30d_cents": 0, "days_sales_outstanding": 90.0, "health": "critical"},
        "revenue": {"total_deals_cents": 10000000, "won_deals_30d_cents": 0, "pipeline_deals_cents": 50000000, "active_customers": 2, "mrr_cents": None, "trend": "declining"},
        "overall_health": "critical",
        "alert_count": 12,
        "correlation_count": 4,
        "connectors_ok": {"erpnext": True, "hubspot": True, "quickbooks": True},
        "raw_snapshots": {},
    }


# ===========================================================================
# Parametrized Input Generators (for hypothesis-like coverage)
# ===========================================================================

@pytest.fixture
def arbitrary_state_inputs() -> List[Dict[str, Any]]:
    """A broad set of state dicts to stress-test invariants.

    Includes: empty dicts, None values, negative counts, extreme numbers,
    missing keys, and malformed structures.
    """
    return [
        {},                                                          # completely empty
        {"support": {}},                                             # partial
        {"support": None},                                           # None domain
        {"support": {"unresolved_issues": -1}},                      # negative count
        {"execution": {"overdue_tasks": 0, "health": "on_track"}},
        {"finance": {"total_overdue_cents": 0, "days_sales_outstanding": None}},
        {"revenue": {"trend": "stable"}},
        {"team": {"departures_30d": 0}},
        {"support": {"unresolved_issues": 1000000}},                 # extreme
        {"execution": {"overdue_tasks": -5}},                        # negative
        {"finance": {"total_overdue_cents": 999999999999}},         # huge
        {"revenue": {"trend": "declining", "won_deals_30d_cents": -1}},
        {"connectors_ok": {"erpnext": True, "hubspot": False}},
        {"tenant_id": "", "run_id": ""},                             # empty strings
        {"tenant_id": "t" * 10000},                                  # very long
        {
            "support": {"unresolved_issues": 50, "sla_breach_count": 10},
            "execution": {"overdue_tasks": 20, "health": "blocked"},
            "finance": {"total_overdue_cents": 99_000_000},
            "revenue": {"trend": "declining"},
            "team": {"departures_30d": 10},
        },                                                           # everything bad
    ]
