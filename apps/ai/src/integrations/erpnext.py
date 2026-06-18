"""
ERPNext Integration Module for Startup Guardian.

Provides startup health snapshot data from ERPNext covering four dimensions:
  - Support state (Issue DocType)
  - Execution state (Project + Task DocTypes)
  - Team state (Employee DocType)
  - Finance state (Sales Invoice DocType)

Supports MOCK MODE for development/testing without a live ERPNext instance.

Environment Variables:
    ERPNEXT_URL: Base URL of the ERPNext instance (default: http://localhost:8080)
    ERPNEXT_API_KEY: API key for token auth (falls back to ERPNEXT_USER)
    ERPNEXT_API_SECRET: API secret for token auth (falls back to ERPNEXT_PASSWORD)

Mock Mode:
    When ERPNEXT_URL is empty or not set, returns realistic seed data
    for development and testing purposes.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from .erpnext_client import ERPNextClient, ERPNextError

logger = logging.getLogger(__name__)

# Mock mode flag - True when ERPNext URL is not configured
MOCK_MODE: bool = not bool(os.getenv("ERPNEXT_URL", "").strip())

# ---------------------------------------------------------------------------
# Realistic mock seed data for development/testing
# ---------------------------------------------------------------------------

_MOCK_SUPPORT_DATA: Dict[str, Any] = {
    "support_open_issues": 12,
    "support_unresolved_issues": 18,
    "support_open_priority_issues": 3,
}

_MOCK_EXECUTION_DATA: Dict[str, Any] = {
    "execution_active_projects": 4,
    "execution_overdue_tasks": 7,
    "execution_milestones_total": 15,
    "execution_milestones_completed": 9,
    "execution_avg_completion": 62.5,
}

_MOCK_TEAM_DATA: Dict[str, Any] = {
    "team_active_count": 18,
    "team_departments": {
        "Engineering": 8,
        "Product": 3,
        "Design": 2,
        "Marketing": 3,
        "Operations": 2,
    },
    "team_new_joinees_30d": 2,
}

_MOCK_FINANCE_DATA: Dict[str, Any] = {
    "finance_unpaid_cents": 2400000,       # INR 24,000
    "finance_overdue_cents": 850000,        # INR 8,500
    "finance_total_outstanding_cents": 3250000,  # INR 32,500
}

_DEFAULT_SNAPSHOT: Dict[str, Any] = {
    **_MOCK_SUPPORT_DATA,
    **_MOCK_EXECUTION_DATA,
    **_MOCK_TEAM_DATA,
    **_MOCK_FINANCE_DATA,
}


def _add_metadata(data: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Add common metadata fields to integration responses."""
    result = data.copy()
    result["source"] = source
    result["fetched_at"] = datetime.utcnow().isoformat() + "Z"
    return result


# ---------------------------------------------------------------------------
# Per-section fetch helpers
# ---------------------------------------------------------------------------


def _fetch_support_state(client: ERPNextClient) -> Dict[str, Any]:
    """Fetch support/issue state from ERPNext Issue DocType."""
    result = {
        "support_open_issues": 0,
        "support_unresolved_issues": 0,
        "support_open_priority_issues": 0,
    }

    try:
        count = client.count("Issue", [["status", "!=", "Closed"]])
        result["support_open_issues"] = count
    except ERPNextError as e:
        logger.warning("Failed to count open issues: %s", e)

    try:
        count = client.count("Issue", [
            ["status", "!=", "Closed"],
            ["status", "!=", "Resolved"],
        ])
        result["support_unresolved_issues"] = count
    except ERPNextError as e:
        logger.warning("Failed to count unresolved issues: %s", e)

    try:
        count = client.count("Issue", [
            ["priority", "=", "High"],
            ["status", "!=", "Closed"],
            ["status", "!=", "Resolved"],
        ])
        result["support_open_priority_issues"] = count
    except ERPNextError as e:
        logger.warning("Failed to count priority issues: %s", e)

    return result


def _fetch_execution_state(client: ERPNextClient) -> Dict[str, Any]:
    """Fetch project/task execution state from Project and Task DocTypes."""
    result = {
        "execution_active_projects": 0,
        "execution_overdue_tasks": 0,
        "execution_milestones_total": 0,
        "execution_milestones_completed": 0,
        "execution_avg_completion": 0.0,
    }

    try:
        count = client.count("Project", [["status", "=", "Open"]])
        result["execution_active_projects"] = count
    except ERPNextError as e:
        logger.warning("Failed to count active projects: %s", e)

    try:
        projects = client.list(
            "Project",
            filters=[["status", "=", "Open"]],
            fields=["name", "percent_complete"],
            limit=1000,
        )
        if projects:
            values = [p.get("percent_complete", 0) or 0 for p in projects]
            result["execution_avg_completion"] = round(sum(values) / len(values), 1)
    except ERPNextError as e:
        logger.warning("Failed to fetch project completion data: %s", e)

    try:
        count = client.count("Task", [["status", "=", "Overdue"]])
        result["execution_overdue_tasks"] = count
    except ERPNextError as e:
        logger.warning("Failed to count overdue tasks: %s", e)

    try:
        count = client.count("Task", [["is_milestone", "=", 1]])
        result["execution_milestones_total"] = count
    except ERPNextError as e:
        logger.warning("Failed to count milestones: %s", e)

    try:
        count = client.count("Task", [
            ["is_milestone", "=", 1],
            ["status", "=", "Completed"],
        ])
        result["execution_milestones_completed"] = count
    except ERPNextError as e:
        logger.warning("Failed to count completed milestones: %s", e)

    return result


def _fetch_team_state(client: ERPNextClient) -> Dict[str, Any]:
    """Fetch employee/team state from ERPNext Employee DocType."""
    result = {
        "team_active_count": 0,
        "team_departments": {},
        "team_new_joinees_30d": 0,
    }

    try:
        count = client.count("Employee", [["status", "=", "Active"]])
        result["team_active_count"] = count
    except ERPNextError as e:
        logger.warning("Failed to count active employees: %s", e)

    try:
        employees = client.list(
            "Employee",
            filters=[["status", "=", "Active"]],
            fields=["name", "department", "date_of_joining"],
            limit=5000,
        )
        dept_counts: Dict[str, int] = {}
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        new_joinees = 0

        for emp in employees:
            dept = emp.get("department") or "Unassigned"
            dept_counts[dept] = dept_counts.get(dept, 0) + 1

            doj = emp.get("date_of_joining")
            if doj:
                try:
                    join_date = datetime.strptime(str(doj)[:10], "%Y-%m-%d")
                    if join_date >= thirty_days_ago:
                        new_joinees += 1
                except (ValueError, TypeError):
                    pass

        result["team_departments"] = dept_counts
        result["team_new_joinees_30d"] = new_joinees
    except ERPNextError as e:
        logger.warning("Failed to fetch employee details: %s", e)

    return result


def _fetch_finance_state(client: ERPNextClient) -> Dict[str, Any]:
    """Fetch finance state from ERPNext Sales Invoice DocType."""
    result = {
        "finance_unpaid_cents": 0,
        "finance_overdue_cents": 0,
        "finance_total_outstanding_cents": 0,
    }

    try:
        unpaid = client.list(
            "Sales Invoice",
            filters=[["status", "in", ["Unpaid", "Partly Paid"]]],
            fields=["name", "outstanding_amount"],
            limit=5000,
        )
        unpaid_total = sum(
            float(inv.get("outstanding_amount", 0) or 0) for inv in unpaid
        )
        result["finance_unpaid_cents"] = int(unpaid_total * 100)
    except ERPNextError as e:
        logger.warning("Failed to fetch unpaid invoices: %s", e)

    try:
        overdue = client.list(
            "Sales Invoice",
            filters=[["status", "=", "Overdue"]],
            fields=["name", "outstanding_amount"],
            limit=5000,
        )
        overdue_total = sum(
            float(inv.get("outstanding_amount", 0) or 0) for inv in overdue
        )
        result["finance_overdue_cents"] = int(overdue_total * 100)
    except ERPNextError as e:
        logger.warning("Failed to fetch overdue invoices: %s", e)

    try:
        all_outstanding = client.list(
            "Sales Invoice",
            filters=[["status", "in", ["Unpaid", "Partly Paid", "Overdue"]]],
            fields=["name", "outstanding_amount"],
            limit=5000,
        )
        outstanding_total = sum(
            float(inv.get("outstanding_amount", 0) or 0) for inv in all_outstanding
        )
        result["finance_total_outstanding_cents"] = int(outstanding_total * 100)
    except ERPNextError as e:
        logger.warning("Failed to fetch total outstanding: %s", e)

    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def get_erpnext_snapshot(tenant_id: str) -> Dict[str, Any]:
    """Get ERPNext snapshot for a tenant covering support, execution, team, and finance.

    Fetches data from the ERPNext instance and returns a flat dict with
    namespaced keys. Each DocType call is individually wrapped in try/except
    so that a single failure doesn't collapse the entire snapshot.

    Args:
        tenant_id: Tenant identifier (used for logging, not API calls).

    Returns:
        Dict with keys grouped by namespace (support_*, execution_*, team_*, finance_*)
        plus metadata (source, fetched_at).
    """
    if MOCK_MODE:
        logger.info("[MOCK MODE] Returning seed ERPNext data for tenant %s", tenant_id)
        return _add_metadata(_DEFAULT_SNAPSHOT, "erpnext_mock")

    # In production, client creation failure is a configuration error —
    # propagate it so the orchestrator sees the failure clearly.
    client = ERPNextClient()

    support = _fetch_support_state(client)
    execution = _fetch_execution_state(client)
    team = _fetch_team_state(client)
    finance = _fetch_finance_state(client)

    result = {**support, **execution, **team, **finance}

    logger.info(
        "ERPNext snapshot for %s: "
        "support=%d unresolved, "
        "execution=%d active projects, "
        "team=%d active, "
        "finance=₹%d outstanding",
        tenant_id,
        result.get("support_unresolved_issues", 0),
        result.get("execution_active_projects", 0),
        result.get("team_active_count", 0),
        result.get("finance_total_outstanding_cents", 0) // 100,
    )

    return _add_metadata(result, "erpnext")
