"""Golden trajectory dataset for Startup Guardian deterministic testing.

Each scenario defines the expected behavior of the orchestrator:
- Which connectors are called and in what order
- What raw snapshots each connector returns
- Which assemblers process each snapshot
- Expected overall health, alerts, and correlations

Usage:
    from tests.deterministic.golden_trajectories import GOLDEN_TRAJECTORIES, TrajectoryScenario

    for scenario in GOLDEN_TRAJECTORIES:
        result = await run_startup_guardian("test-tenant")
        # assert against scenario.expected_*
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TrajectoryScenario:
    """A single deterministic test scenario for the Startup Guardian orchestrator."""

    name: str
    description: str
    connector_order: list[str]
    connectors_ok: dict[str, bool]
    expected_assemblers: list[str]
    expected_health: str
    expected_alerts: list[str]
    expected_correlations: list[str]
    raw_snapshots: dict[str, dict[str, Any]]


# ---------------------------------------------------------------------------
# Default / base snapshot values (all zeros = healthy)
# ---------------------------------------------------------------------------

_ERPNEXT_BASE: dict[str, Any] = {
    "support_open_issues": 0,
    "support_unresolved_issues": 0,
    "support_open_priority_issues": 0,
    "execution_active_projects": 0,
    "execution_overdue_tasks": 0,
    "execution_milestones_total": 0,
    "execution_milestones_completed": 0,
    "execution_avg_completion": 0,
    "team_active_count": 0,
    "team_departments": {},
    "team_new_joinees_30d": 0,
    "team_departures_30d": 0,
    "finance_unpaid_cents": 0,
    "finance_overdue_cents": 0,
    "finance_total_outstanding_cents": 0,
}

_HUBSPOT_BASE: dict[str, Any] = {
    "revenue_total_deals_cents": 0,
    "revenue_won_deals_30d_cents": 0,
    "revenue_pipeline_deals_cents": 0,
    "revenue_active_customers": 0,
    "revenue_mrr_cents": None,
}

_QUICKBOOKS_BASE: dict[str, Any] = {
    "finance_outstanding_invoices": 0,
    "finance_total_outstanding_cents": 0,
    "finance_overdue_invoices": 0,
    "finance_overdue_cents": 0,
    "finance_total_overdue_cents": 0,
    "finance_paid_invoices_30d_cents": 0,
    "finance_unpaid_invoices_30d_cents": 0,
    "finance_days_sales_outstanding": None,
}


def _erpnext(**overrides: Any) -> dict[str, Any]:
    """Return an ERPNext snapshot with optional field overrides."""
    return {**_ERPNEXT_BASE, **overrides}


def _hubspot(**overrides: Any) -> dict[str, Any]:
    """Return a HubSpot snapshot with optional field overrides."""
    return {**_HUBSPOT_BASE, **overrides}


def _quickbooks(**overrides: Any) -> dict[str, Any]:
    """Return a QuickBooks snapshot with optional field overrides."""
    return {**_QUICKBOOKS_BASE, **overrides}


# ---------------------------------------------------------------------------
# All 15 golden trajectory scenarios
# ---------------------------------------------------------------------------

ALL_HEALTHY = TrajectoryScenario(
    name="all_healthy",
    description="All connectors succeed, all domains good → health=good, no alerts",
    connector_order=["erpnext", "hubspot", "quickbooks"],
    connectors_ok={"erpnext": True, "hubspot": True, "quickbooks": True},
    expected_assemblers=[
        "assemble_support_state",
        "assemble_execution_state",
        "assemble_team_state",
        "assemble_finance_state",
        "assemble_revenue_state",
        "assemble_finance_state",  # quickbooks overwrites finance
    ],
    expected_health="good",
    expected_alerts=[],
    expected_correlations=[],
    raw_snapshots={
        "erpnext": _erpnext(
            support_open_issues=5,
            support_unresolved_issues=0,
            execution_active_projects=3,
            execution_overdue_tasks=0,
            execution_milestones_total=10,
            execution_milestones_completed=7,
            execution_avg_completion=70.0,
            team_active_count=15,
            team_departments={"Engineering": 8, "Product": 4, "Design": 3},
            team_new_joinees_30d=2,
            team_departures_30d=0,
            finance_unpaid_cents=0,
            finance_overdue_cents=0,
            finance_total_outstanding_cents=100_000,
        ),
        "hubspot": _hubspot(
            revenue_total_deals_cents=500_000_00,
            revenue_won_deals_30d_cents=150_000_00,
            revenue_pipeline_deals_cents=350_000_00,
            revenue_active_customers=12,
            revenue_mrr_cents=420_000_00,
        ),
        "quickbooks": _quickbooks(
            finance_outstanding_invoices=5,
            finance_total_outstanding_cents=200_000_00,
            finance_overdue_invoices=0,
            finance_total_overdue_cents=0,
            finance_paid_invoices_30d_cents=180_000_00,
            finance_unpaid_invoices_30d_cents=200_000_00,
            finance_days_sales_outstanding=33.0,
        ),
    },
)

SUPPORT_CRITICAL = TrajectoryScenario(
    name="support_critical",
    description="ERPNext returns 20 unresolved issues → health=critical, alert SG-SUP-01",
    connector_order=["erpnext", "hubspot", "quickbooks"],
    connectors_ok={"erpnext": True, "hubspot": True, "quickbooks": True},
    expected_assemblers=[
        "assemble_support_state",
        "assemble_execution_state",
        "assemble_team_state",
        "assemble_finance_state",
        "assemble_revenue_state",
        "assemble_finance_state",
    ],
    expected_health="critical",
    expected_alerts=["SG-SUP-01"],
    expected_correlations=[],
    raw_snapshots={
        "erpnext": _erpnext(
            support_open_issues=25,
            support_unresolved_issues=20,
            execution_active_projects=3,
            execution_overdue_tasks=1,
            execution_milestones_total=10,
            execution_milestones_completed=7,
            execution_avg_completion=70.0,
            team_active_count=15,
            team_departments={"Engineering": 8, "Product": 4, "Design": 3},
            team_new_joinees_30d=1,
            team_departures_30d=0,
            finance_unpaid_cents=0,
            finance_overdue_cents=0,
            finance_total_outstanding_cents=50_000_00,
        ),
        "hubspot": _hubspot(
            revenue_total_deals_cents=500_000_00,
            revenue_won_deals_30d_cents=150_000_00,
            revenue_pipeline_deals_cents=350_000_00,
            revenue_active_customers=10,
            revenue_mrr_cents=300_000_00,
        ),
        "quickbooks": _quickbooks(
            finance_outstanding_invoices=3,
            finance_total_outstanding_cents=150_000_00,
            finance_overdue_invoices=0,
            finance_total_overdue_cents=0,
            finance_paid_invoices_30d_cents=120_000_00,
            finance_unpaid_invoices_30d_cents=150_000_00,
            finance_days_sales_outstanding=37.0,
        ),
    },
)

FINANCE_CRITICAL = TrajectoryScenario(
    name="finance_critical",
    description="ERPNext returns ₹20k overdue → health=critical, alert SG-FIN-01",
    connector_order=["erpnext", "hubspot", "quickbooks"],
    connectors_ok={"erpnext": True, "hubspot": True, "quickbooks": True},
    expected_assemblers=[
        "assemble_support_state",
        "assemble_execution_state",
        "assemble_team_state",
        "assemble_finance_state",
        "assemble_revenue_state",
        "assemble_finance_state",
    ],
    expected_health="critical",
    expected_alerts=["SG-FIN-01"],
    expected_correlations=[],
    raw_snapshots={
        "erpnext": _erpnext(
            support_open_issues=5,
            support_unresolved_issues=2,
            execution_active_projects=3,
            execution_overdue_tasks=1,
            execution_milestones_total=10,
            execution_milestones_completed=7,
            execution_avg_completion=70.0,
            team_active_count=15,
            team_departments={"Engineering": 8, "Product": 4, "Design": 3},
            team_new_joinees_30d=1,
            team_departures_30d=0,
            finance_unpaid_cents=6_000_000,
            finance_overdue_cents=6_000_000,
            finance_total_outstanding_cents=500_000_00,
        ),
        "hubspot": _hubspot(
            revenue_total_deals_cents=500_000_00,
            revenue_won_deals_30d_cents=150_000_00,
            revenue_pipeline_deals_cents=350_000_00,
            revenue_active_customers=10,
            revenue_mrr_cents=300_000_00,
        ),
        "quickbooks": _quickbooks(
            finance_outstanding_invoices=8,
            finance_total_outstanding_cents=500_000_00,
            finance_overdue_invoices=5,
            finance_overdue_cents=6_000_000,
            finance_total_overdue_cents=6_000_000,
            finance_paid_invoices_30d_cents=120_000_00,
            finance_unpaid_invoices_30d_cents=500_000_00,
            finance_days_sales_outstanding=50.0,
        ),
    },
)

REVENUE_DECLINING = TrajectoryScenario(
    name="revenue_declining",
    description="HubSpot returns declining trend → health=attention, alert SG-REV-01",
    connector_order=["erpnext", "hubspot", "quickbooks"],
    connectors_ok={"erpnext": True, "hubspot": True, "quickbooks": True},
    expected_assemblers=[
        "assemble_support_state",
        "assemble_execution_state",
        "assemble_team_state",
        "assemble_finance_state",
        "assemble_revenue_state",
        "assemble_finance_state",
    ],
    expected_health="attention",
    expected_alerts=["SG-REV-01"],
    expected_correlations=["SG-CR-05"],
    raw_snapshots={
        "erpnext": _erpnext(
            support_open_issues=5,
            support_unresolved_issues=2,
            execution_active_projects=3,
            execution_overdue_tasks=1,
            execution_milestones_total=10,
            execution_milestones_completed=7,
            execution_avg_completion=70.0,
            team_active_count=15,
            team_departments={"Engineering": 8, "Product": 4, "Design": 3},
            team_new_joinees_30d=1,
            team_departures_30d=0,
            finance_unpaid_cents=0,
            finance_overdue_cents=0,
            finance_total_outstanding_cents=100_000_00,
        ),
        "hubspot": _hubspot(
            revenue_total_deals_cents=500_000_00,
            revenue_won_deals_30d_cents=0,  # no wins → declining
            revenue_pipeline_deals_cents=500_000_00,
            revenue_active_customers=10,
            revenue_mrr_cents=300_000_00,
        ),
        "quickbooks": _quickbooks(
            finance_outstanding_invoices=3,
            finance_total_outstanding_cents=150_000_00,
            finance_overdue_invoices=0,
            finance_overdue_cents=0,
            finance_total_overdue_cents=0,
            finance_paid_invoices_30d_cents=120_000_00,
            finance_unpaid_invoices_30d_cents=150_000_00,
            finance_days_sales_outstanding=37.0,
        ),
    },
)

ERPNEXT_FAILS = TrajectoryScenario(
    name="erpnext_fails",
    description="ERPNext connector fails → only hubspot+quickbooks, health=good",
    connector_order=["erpnext", "hubspot", "quickbooks"],
    connectors_ok={"erpnext": False, "hubspot": True, "quickbooks": True},
    expected_assemblers=[
        "assemble_revenue_state",
        "assemble_finance_state",
    ],
    expected_health="good",
    expected_alerts=[],
    expected_correlations=[],
    raw_snapshots={
        "hubspot": _hubspot(
            revenue_total_deals_cents=500_000_00,
            revenue_won_deals_30d_cents=150_000_00,
            revenue_pipeline_deals_cents=350_000_00,
            revenue_active_customers=10,
            revenue_mrr_cents=300_000_00,
        ),
        "quickbooks": _quickbooks(
            finance_outstanding_invoices=3,
            finance_total_outstanding_cents=150_000_00,
            finance_overdue_invoices=0,
            finance_total_overdue_cents=0,
            finance_paid_invoices_30d_cents=120_000_00,
            finance_unpaid_invoices_30d_cents=150_000_00,
            finance_days_sales_outstanding=37.0,
        ),
    },
)

HUBSPOT_FAILS = TrajectoryScenario(
    name="hubspot_fails",
    description="HubSpot connector fails → only erpnext+quickbooks, health=good",
    connector_order=["erpnext", "hubspot", "quickbooks"],
    connectors_ok={"erpnext": True, "hubspot": False, "quickbooks": True},
    expected_assemblers=[
        "assemble_support_state",
        "assemble_execution_state",
        "assemble_team_state",
        "assemble_finance_state",
        "assemble_finance_state",
    ],
    expected_health="good",
    expected_alerts=[],
    expected_correlations=[],
    raw_snapshots={
        "erpnext": _erpnext(
            support_open_issues=5,
            support_unresolved_issues=0,
            execution_active_projects=3,
            execution_overdue_tasks=0,
            execution_milestones_total=10,
            execution_milestones_completed=7,
            execution_avg_completion=70.0,
            team_active_count=15,
            team_departments={"Engineering": 8, "Product": 4, "Design": 3},
            team_new_joinees_30d=1,
            team_departures_30d=0,
            finance_unpaid_cents=0,
            finance_overdue_cents=0,
            finance_total_outstanding_cents=100_000_00,
        ),
        "quickbooks": _quickbooks(
            finance_outstanding_invoices=3,
            finance_total_outstanding_cents=150_000_00,
            finance_overdue_invoices=0,
            finance_total_overdue_cents=0,
            finance_paid_invoices_30d_cents=120_000_00,
            finance_unpaid_invoices_30d_cents=150_000_00,
            finance_days_sales_outstanding=37.0,
        ),
    },
)

QUICKBOOKS_FAILS = TrajectoryScenario(
    name="quickbooks_fails",
    description="QuickBooks connector fails → only erpnext+hubspot, health=good",
    connector_order=["erpnext", "hubspot", "quickbooks"],
    connectors_ok={"erpnext": True, "hubspot": True, "quickbooks": False},
    expected_assemblers=[
        "assemble_support_state",
        "assemble_execution_state",
        "assemble_team_state",
        "assemble_finance_state",
        "assemble_revenue_state",
    ],
    expected_health="good",
    expected_alerts=[],
    expected_correlations=[],
    raw_snapshots={
        "erpnext": _erpnext(
            support_open_issues=5,
            support_unresolved_issues=0,
            execution_active_projects=3,
            execution_overdue_tasks=0,
            execution_milestones_total=10,
            execution_milestones_completed=7,
            execution_avg_completion=70.0,
            team_active_count=15,
            team_departments={"Engineering": 8, "Product": 4, "Design": 3},
            team_new_joinees_30d=1,
            team_departures_30d=0,
            finance_unpaid_cents=0,
            finance_overdue_cents=0,
            finance_total_outstanding_cents=100_000_00,
        ),
        "hubspot": _hubspot(
            revenue_total_deals_cents=500_000_00,
            revenue_won_deals_30d_cents=150_000_00,
            revenue_pipeline_deals_cents=350_000_00,
            revenue_active_customers=10,
            revenue_mrr_cents=300_000_00,
        ),
    },
)

ALL_FAIL = TrajectoryScenario(
    name="all_fail",
    description="All connectors fail → all defaults, health=good",
    connector_order=["erpnext", "hubspot", "quickbooks"],
    connectors_ok={"erpnext": False, "hubspot": False, "quickbooks": False},
    expected_assemblers=[],
    expected_health="good",
    expected_alerts=[],
    expected_correlations=[],
    raw_snapshots={},
)

EMPTY_DB = TrajectoryScenario(
    name="empty_db",
    description="All connectors return zero values → health=good",
    connector_order=["erpnext", "hubspot", "quickbooks"],
    connectors_ok={"erpnext": True, "hubspot": True, "quickbooks": True},
    expected_assemblers=[
        "assemble_support_state",
        "assemble_execution_state",
        "assemble_team_state",
        "assemble_finance_state",
        "assemble_revenue_state",
        "assemble_finance_state",
    ],
    expected_health="good",
    expected_alerts=[],
    expected_correlations=[],
    raw_snapshots={
        "erpnext": _erpnext(),
        "hubspot": _hubspot(),
        "quickbooks": _quickbooks(),
    },
)

HIGH_ATTRITION = TrajectoryScenario(
    name="high_attrition",
    description="ERPNext returns 5 departures → alert SG-TEAM-01",
    connector_order=["erpnext", "hubspot", "quickbooks"],
    connectors_ok={"erpnext": True, "hubspot": True, "quickbooks": True},
    expected_assemblers=[
        "assemble_support_state",
        "assemble_execution_state",
        "assemble_team_state",
        "assemble_finance_state",
        "assemble_revenue_state",
        "assemble_finance_state",
    ],
    expected_health="critical",
    expected_alerts=["SG-TEAM-01"],
    expected_correlations=[],
    raw_snapshots={
        "erpnext": _erpnext(
            support_open_issues=5,
            support_unresolved_issues=1,
            execution_active_projects=3,
            execution_overdue_tasks=1,
            execution_milestones_total=10,
            execution_milestones_completed=7,
            execution_avg_completion=70.0,
            team_active_count=15,
            team_departments={"Engineering": 8, "Product": 4, "Design": 3},
            team_new_joinees_30d=0,
            team_departures_30d=5,
            finance_unpaid_cents=0,
            finance_overdue_cents=0,
            finance_total_outstanding_cents=100_000_00,
        ),
        "hubspot": _hubspot(
            revenue_total_deals_cents=500_000_00,
            revenue_won_deals_30d_cents=150_000_00,
            revenue_pipeline_deals_cents=350_000_00,
            revenue_active_customers=10,
            revenue_mrr_cents=300_000_00,
        ),
        "quickbooks": _quickbooks(
            finance_outstanding_invoices=3,
            finance_total_outstanding_cents=150_000_00,
            finance_overdue_invoices=0,
            finance_total_overdue_cents=0,
            finance_paid_invoices_30d_cents=120_000_00,
            finance_unpaid_invoices_30d_cents=150_000_00,
            finance_days_sales_outstanding=37.0,
        ),
    },
)

DSO_WARNING = TrajectoryScenario(
    name="dso_warning",
    description="QuickBooks returns DSO=70 → alert SG-FIN-02",
    connector_order=["erpnext", "hubspot", "quickbooks"],
    connectors_ok={"erpnext": True, "hubspot": True, "quickbooks": True},
    expected_assemblers=[
        "assemble_support_state",
        "assemble_execution_state",
        "assemble_team_state",
        "assemble_finance_state",
        "assemble_revenue_state",
        "assemble_finance_state",
    ],
    expected_health="good",
    expected_alerts=["SG-FIN-02"],
    expected_correlations=[],
    raw_snapshots={
        "erpnext": _erpnext(
            support_open_issues=5,
            support_unresolved_issues=0,
            execution_active_projects=3,
            execution_overdue_tasks=0,
            execution_milestones_total=10,
            execution_milestones_completed=7,
            execution_avg_completion=70.0,
            team_active_count=15,
            team_departments={"Engineering": 8, "Product": 4, "Design": 3},
            team_new_joinees_30d=1,
            team_departures_30d=0,
            finance_unpaid_cents=0,
            finance_overdue_cents=0,
            finance_total_outstanding_cents=100_000_00,
        ),
        "hubspot": _hubspot(
            revenue_total_deals_cents=500_000_00,
            revenue_won_deals_30d_cents=150_000_00,
            revenue_pipeline_deals_cents=350_000_00,
            revenue_active_customers=10,
            revenue_mrr_cents=300_000_00,
        ),
        "quickbooks": _quickbooks(
            finance_outstanding_invoices=10,
            finance_total_outstanding_cents=500_000_00,
            finance_overdue_invoices=0,
            finance_total_overdue_cents=0,
            finance_paid_invoices_30d_cents=214_000_00,
            finance_unpaid_invoices_30d_cents=500_000_00,
            finance_days_sales_outstanding=70.0,
        ),
    },
)

EXECUTION_BLOCKED = TrajectoryScenario(
    name="execution_blocked",
    description="ERPNext returns health=blocked → alert SG-EXE-02",
    connector_order=["erpnext", "hubspot", "quickbooks"],
    connectors_ok={"erpnext": True, "hubspot": True, "quickbooks": True},
    expected_assemblers=[
        "assemble_support_state",
        "assemble_execution_state",
        "assemble_team_state",
        "assemble_finance_state",
        "assemble_revenue_state",
        "assemble_finance_state",
    ],
    expected_health="critical",
    expected_alerts=["SG-EXE-01", "SG-EXE-02"],
    expected_correlations=[],
    raw_snapshots={
        "erpnext": _erpnext(
            support_open_issues=5,
            support_unresolved_issues=2,
            execution_active_projects=4,
            execution_overdue_tasks=7,
            execution_milestones_total=15,
            execution_milestones_completed=3,
            execution_avg_completion=20.0,
            team_active_count=15,
            team_departments={"Engineering": 8, "Product": 4, "Design": 3},
            team_new_joinees_30d=1,
            team_departures_30d=1,
            finance_unpaid_cents=0,
            finance_overdue_cents=0,
            finance_total_outstanding_cents=100_000_00,
        ),
        "hubspot": _hubspot(
            revenue_total_deals_cents=500_000_00,
            revenue_won_deals_30d_cents=150_000_00,
            revenue_pipeline_deals_cents=350_000_00,
            revenue_active_customers=10,
            revenue_mrr_cents=300_000_00,
        ),
        "quickbooks": _quickbooks(
            finance_outstanding_invoices=3,
            finance_total_outstanding_cents=150_000_00,
            finance_overdue_invoices=0,
            finance_overdue_cents=0,
            finance_total_overdue_cents=0,
            finance_paid_invoices_30d_cents=120_000_00,
            finance_unpaid_invoices_30d_cents=150_000_00,
            finance_days_sales_outstanding=37.0,
        ),
    },
)

MULTI_DOMAIN_CRITICAL = TrajectoryScenario(
    name="multi_domain_critical",
    description="Support+Finance+Execution all critical → health=critical",
    connector_order=["erpnext", "hubspot", "quickbooks"],
    connectors_ok={"erpnext": True, "hubspot": True, "quickbooks": True},
    expected_assemblers=[
        "assemble_support_state",
        "assemble_execution_state",
        "assemble_team_state",
        "assemble_finance_state",
        "assemble_revenue_state",
        "assemble_finance_state",
    ],
    expected_health="critical",
    expected_alerts=["SG-SUP-01", "SG-FIN-01", "SG-EXE-01", "SG-EXE-02"],
    expected_correlations=["SG-CR-01", "SG-CR-03"],
    raw_snapshots={
        "erpnext": _erpnext(
            support_open_issues=30,
            support_unresolved_issues=20,
            execution_active_projects=5,
            execution_overdue_tasks=8,
            execution_milestones_total=20,
            execution_milestones_completed=4,
            execution_avg_completion=20.0,
            team_active_count=15,
            team_departments={"Engineering": 8, "Product": 4, "Design": 3},
            team_new_joinees_30d=0,
            team_departures_30d=0,
            finance_unpaid_cents=6_000_000,
            finance_overdue_cents=6_000_000,
            finance_total_outstanding_cents=600_000_00,
        ),
        "hubspot": _hubspot(
            revenue_total_deals_cents=500_000_00,
            revenue_won_deals_30d_cents=150_000_00,
            revenue_pipeline_deals_cents=350_000_00,
            revenue_active_customers=10,
            revenue_mrr_cents=300_000_00,
        ),
        "quickbooks": _quickbooks(
            finance_outstanding_invoices=10,
            finance_total_outstanding_cents=600_000_00,
            finance_overdue_invoices=6,
            finance_overdue_cents=6_000_000,
            finance_total_overdue_cents=6_000_000,
            finance_paid_invoices_30d_cents=120_000_00,
            finance_unpaid_invoices_30d_cents=600_000_00,
            finance_days_sales_outstanding=60.0,
        ),
    },
)

CORRELATION_TEAM_FINANCE = TrajectoryScenario(
    name="correlation_team_finance",
    description="Team departures=2 + Finance overdue>₹50k → correlation SG-CR-04",
    connector_order=["erpnext", "hubspot", "quickbooks"],
    connectors_ok={"erpnext": True, "hubspot": True, "quickbooks": True},
    expected_assemblers=[
        "assemble_support_state",
        "assemble_execution_state",
        "assemble_team_state",
        "assemble_finance_state",
        "assemble_revenue_state",
        "assemble_finance_state",
    ],
    expected_health="critical",
    expected_alerts=["SG-FIN-01", "SG-TEAM-01"],
    expected_correlations=["SG-CR-04"],
    raw_snapshots={
        "erpnext": _erpnext(
            support_open_issues=5,
            support_unresolved_issues=2,
            execution_active_projects=3,
            execution_overdue_tasks=1,
            execution_milestones_total=10,
            execution_milestones_completed=7,
            execution_avg_completion=70.0,
            team_active_count=15,
            team_departments={"Engineering": 8, "Product": 4, "Design": 3},
            team_new_joinees_30d=0,
            team_departures_30d=3,
            finance_unpaid_cents=6_000_000,
            finance_overdue_cents=6_000_000,
            finance_total_outstanding_cents=600_000_00,
        ),
        "hubspot": _hubspot(
            revenue_total_deals_cents=500_000_00,
            revenue_won_deals_30d_cents=150_000_00,
            revenue_pipeline_deals_cents=350_000_00,
            revenue_active_customers=10,
            revenue_mrr_cents=300_000_00,
        ),
        "quickbooks": _quickbooks(
            finance_outstanding_invoices=8,
            finance_total_outstanding_cents=600_000_00,
            finance_overdue_invoices=5,
            finance_overdue_cents=6_000_000,
            finance_total_overdue_cents=6_000_000,
            finance_paid_invoices_30d_cents=120_000_00,
            finance_unpaid_invoices_30d_cents=600_000_00,
            finance_days_sales_outstanding=60.0,
        ),
    },
)

CORRELATION_REVENUE_EXEC = TrajectoryScenario(
    name="correlation_revenue_exec",
    description="Revenue declining + Execution at_risk → correlation SG-CR-05",
    connector_order=["erpnext", "hubspot", "quickbooks"],
    connectors_ok={"erpnext": True, "hubspot": True, "quickbooks": True},
    expected_assemblers=[
        "assemble_support_state",
        "assemble_execution_state",
        "assemble_team_state",
        "assemble_finance_state",
        "assemble_revenue_state",
        "assemble_finance_state",
    ],
    expected_health="attention",
    expected_alerts=["SG-REV-01"],
    expected_correlations=["SG-CR-05"],
    raw_snapshots={
        "erpnext": _erpnext(
            support_open_issues=5,
            support_unresolved_issues=2,
            execution_active_projects=4,
            execution_overdue_tasks=2,
            execution_milestones_total=12,
            execution_milestones_completed=5,
            execution_avg_completion=42.0,
            team_active_count=15,
            team_departments={"Engineering": 8, "Product": 4, "Design": 3},
            team_new_joinees_30d=1,
            team_departures_30d=0,
            finance_unpaid_cents=0,
            finance_overdue_cents=0,
            finance_total_outstanding_cents=100_000_00,
        ),
        "hubspot": _hubspot(
            revenue_total_deals_cents=500_000_00,
            revenue_won_deals_30d_cents=0,
            revenue_pipeline_deals_cents=500_000_00,
            revenue_active_customers=10,
            revenue_mrr_cents=300_000_00,
        ),
        "quickbooks": _quickbooks(
            finance_outstanding_invoices=3,
            finance_total_outstanding_cents=150_000_00,
            finance_overdue_invoices=0,
            finance_total_overdue_cents=0,
            finance_paid_invoices_30d_cents=120_000_00,
            finance_unpaid_invoices_30d_cents=150_000_00,
            finance_days_sales_outstanding=37.0,
        ),
    },
)

# ---------------------------------------------------------------------------
# Master list — import this for parametrized tests
# ---------------------------------------------------------------------------

GOLDEN_TRAJECTORIES: list[TrajectoryScenario] = [
    ALL_HEALTHY,
    SUPPORT_CRITICAL,
    FINANCE_CRITICAL,
    REVENUE_DECLINING,
    ERPNEXT_FAILS,
    HUBSPOT_FAILS,
    QUICKBOOKS_FAILS,
    ALL_FAIL,
    EMPTY_DB,
    HIGH_ATTRITION,
    DSO_WARNING,
    EXECUTION_BLOCKED,
    MULTI_DOMAIN_CRITICAL,
    CORRELATION_TEAM_FINANCE,
    CORRELATION_REVENUE_EXEC,
]

# Lookup by name for convenience
TRAJECTORY_BY_NAME: dict[str, TrajectoryScenario] = {s.name: s for s in GOLDEN_TRAJECTORIES}
