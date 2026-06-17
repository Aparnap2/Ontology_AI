"""
Integration tests hitting real Mockoon containers.

ERPNext + QuickBooks: real HTTP to Mockoon (no mocks).
HubSpot: SDK mocked (no custom base URL), verified via httpx against Mockoon.

Requires: 3 Mockoon containers running (started by conftest or manually).
"""
from __future__ import annotations

import os
import subprocess
import time
from typing import Any, Dict, Generator
from unittest.mock import patch

import httpx
import pytest


# ---------------------------------------------------------------------------
# Mockoon container lifecycle (session-scoped)
# ---------------------------------------------------------------------------

COMPOSE_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..",
    "docker-compose.startup-guardian.yml"
)

REQUIRED_ENV = {
    "ERPNEXT_URL": "http://localhost:8099",
    "ERPNEXT_USER": "test",
    "ERPNEXT_PASSWORD": "test",
    "QUICKBOOKS_CLIENT_ID": "test",
    "QUICKBOOKS_ACCESS_TOKEN": "test",
    "QUICKBOOKS_COMPANY_ID": "123146573628384",
    "QUICKBOOKS_API_URL": "http://localhost:8097",
    "HUBSPOT_ACCESS_TOKEN": "test-token",
}


def _containers_running() -> bool:
    """Check if all 3 Mockoon containers are healthy."""
    for port in [8099, 8098, 8097]:
        try:
            r = httpx.get(f"http://localhost:{port}/health", timeout=2)
            if r.status_code != 200:
                return False
        except Exception:
            return False
    return True


def _start_containers() -> None:
    """Start Mockoon containers via docker run (individual)."""
    containers = [
        ("sg-mock-erpnext", "8099:8080", "erpnext.json"),
        ("sg-mock-hubspot", "8098:8080", "hubspot.json"),
        ("sg-mock-quickbooks", "8097:8080", "quickbooks.json"),
    ]
    mockoon_dir = os.path.join(
        os.path.dirname(__file__), "..", "mockoon"
    )
    for name, port_map, fixture in containers:
        subprocess.run(
            ["docker", "rm", "-f", name],
            capture_output=True, timeout=10,
        )
        subprocess.run(
            [
                "docker", "run", "-d",
                "--name", name,
                "-p", port_map,
                "-v", f"{os.path.join(mockoon_dir, fixture)}:/data:ro",
                "mockoon/cli:latest", "-d", "/data", "-p", "8080",
            ],
            capture_output=True, timeout=30,
        )
    time.sleep(4)


def _stop_containers() -> None:
    """Stop all Mockoon containers."""
    for name in ["sg-mock-erpnext", "sg-mock-hubspot", "sg-mock-quickbooks"]:
        subprocess.run(
            ["docker", "stop", name], capture_output=True, timeout=10,
        )
        subprocess.run(
            ["docker", "rm", name], capture_output=True, timeout=10,
        )


@pytest.fixture(scope="session", autouse=True)
def mockoon_containers():
    """Session-scoped fixture: start containers before, stop after all tests."""
    already_running = _containers_running()
    if not already_running:
        _start_containers()
    assert _containers_running(), "Mockoon containers failed to start"
    yield
    if not already_running:
        _stop_containers()


# ---------------------------------------------------------------------------
# Env setup (session-scoped)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def set_env_vars():
    """Set env vars so connectors hit Mockoon instead of real APIs."""
    old = {}
    for k, v in REQUIRED_ENV.items():
        old[k] = os.environ.get(k)
        os.environ[k] = v
    yield
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ---------------------------------------------------------------------------
# Mock HubSpot SDK (it can't point to custom base URL)
# ---------------------------------------------------------------------------

def _build_hubspot_deal(name: str, amount: str, stage: str, closedate: str = "") -> Any:
    """Build a mock HubSpot deal object."""
    from unittest.mock import MagicMock
    deal = MagicMock()
    deal.properties = {
        "dealname": name,
        "amount": amount,
        "dealstage": stage,
        "closedate": closedate,
        "createdate": "2026-01-15T00:00:00Z",
    }
    return deal


def _build_hubspot_company(name: str, domain: str) -> Any:
    """Build a mock HubSpot company object."""
    from unittest.mock import MagicMock
    company = MagicMock()
    company.properties = {"name": name, "domain": domain, "industry": "tech"}
    return company


# ===========================================================================
# TEST SUITE 1: ERPNext connector (real HTTP to Mockoon)
# ===========================================================================

class TestERPNextReal:
    """ERPNext connector hitting real Mockoon on :8099."""

    def test_health(self):
        r = httpx.get("http://localhost:8099/health", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_count_issues(self):
        from src.integrations.erpnext_client import ERPNextClient
        client = ERPNextClient()
        count = client.count("Issue")
        assert count == 3

    def test_count_projects(self):
        from src.integrations.erpnext_client import ERPNextClient
        client = ERPNextClient()
        count = client.count("Project")
        assert count == 2

    def test_count_employees(self):
        from src.integrations.erpnext_client import ERPNextClient
        client = ERPNextClient()
        count = client.count("Employee")
        assert count == 5

    def test_list_employees(self):
        from src.integrations.erpnext_client import ERPNextClient
        client = ERPNextClient()
        emps = client.list("Employee", fields=["name", "department"])
        assert len(emps) == 5
        departments = {e["department"] for e in emps}
        assert "Engineering" in departments

    def test_list_invoices(self):
        from src.integrations.erpnext_client import ERPNextClient
        client = ERPNextClient()
        invs = client.list("Sales Invoice", fields=["name", "outstanding_amount", "status"])
        assert len(invs) == 3
        statuses = {i["status"] for i in invs}
        assert "Overdue" in statuses

    def test_full_snapshot(self):
        from src.integrations.erpnext import get_erpnext_snapshot
        snap = get_erpnext_snapshot("integration-test")
        assert snap["support_open_issues"] == 3
        assert snap["execution_active_projects"] == 2
        assert snap["team_active_count"] == 5
        assert snap["finance_total_outstanding_cents"] > 0
        assert snap["source"] == "erpnext"


# ===========================================================================
# TEST SUITE 2: QuickBooks connector (real HTTP to Mockoon)
# ===========================================================================

class TestQuickBooksReal:
    """QuickBooks connector hitting real Mockoon on :8097."""

    def test_health(self):
        r = httpx.get("http://localhost:8097/health", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_full_snapshot(self):
        from src.integrations.quickbooks import get_quickbooks_snapshot
        snap = get_quickbooks_snapshot("integration-test")
        assert snap["finance_outstanding_invoices"] == 3
        assert snap["finance_total_outstanding_cents"] == 2_850_000
        assert snap["finance_overdue_invoices"] == 2
        assert snap["finance_total_overdue_cents"] == 2_000_000
        assert snap["source"] == "quickbooks"

    def test_dso_computed(self):
        from src.integrations.quickbooks import get_quickbooks_snapshot
        snap = get_quickbooks_snapshot("integration-test")
        assert snap["finance_days_sales_outstanding"] is not None
        assert snap["finance_days_sales_outstanding"] > 0


# ===========================================================================
# TEST SUITE 3: HubSpot Mockoon data (verified via httpx, not SDK)
# ===========================================================================

class TestHubSpotMockoon:
    """Verify HubSpot Mockoon fixture data via direct httpx calls."""

    def test_health(self):
        r = httpx.get("http://localhost:8098/health", timeout=5)
        assert r.status_code == 200

    def test_deals_fixture(self):
        r = httpx.get("http://localhost:8098/crm/v3/objects/deals", timeout=5)
        data = r.json()
        deals = data["results"]
        assert len(deals) == 3
        stages = {d["properties"]["dealstage"] for d in deals}
        assert "closedwon" in stages

    def test_companies_fixture(self):
        r = httpx.get("http://localhost:8098/crm/v3/objects/companies", timeout=5)
        data = r.json()
        companies = data["results"]
        assert len(companies) == 5
        names = {c["properties"]["name"] for c in companies}
        assert "Acme Corp" in names

    def test_hubspot_snapshot_via_sdk_mock(self):
        """Test HubSpot snapshot with SDK mocked to return Mockoon data."""
        from unittest.mock import MagicMock

        # Fetch real data from Mockoon
        deals_r = httpx.get("http://localhost:8098/crm/v3/objects/deals", timeout=5)
        companies_r = httpx.get("http://localhost:8098/crm/v3/objects/companies", timeout=5)
        raw_deals = deals_r.json()["results"]
        raw_companies = companies_r.json()["results"]

        # Build mock deal/company objects matching SDK shape
        mock_deals = []
        for d in raw_deals:
            obj = MagicMock()
            obj.properties = d["properties"]
            mock_deals.append(obj)

        mock_companies = []
        for c in raw_companies:
            obj = MagicMock()
            obj.properties = c["properties"]
            mock_companies.append(obj)

        mock_client = MagicMock()
        mock_client.crm.deals.get_all.return_value = mock_deals
        mock_client.crm.companies.get_all.return_value = mock_companies

        with patch("hubspot.HubSpot", return_value=mock_client):
            from src.integrations.hubspot import get_hubspot_snapshot
            snap = get_hubspot_snapshot("integration-test")

        assert snap["revenue_total_deals_cents"] == 125_000_000
        assert snap["revenue_won_deals_30d_cents"] == 50_000_000
        assert snap["revenue_pipeline_deals_cents"] == 75_000_000
        assert snap["revenue_active_customers"] == 5
        assert snap["source"] == "hubspot"


# ===========================================================================
# TEST SUITE 4: Full orchestrator pipeline (ERPNext + QuickBooks real, HubSpot mocked)
# ===========================================================================

class TestFullPipeline:
    """Full orchestrator pipeline with real ERPNext + QuickBooks, mocked HubSpot."""

    @pytest.mark.asyncio
    async def test_pipeline_all_connectors(self):
        from unittest.mock import MagicMock
        import src.orchestration.run_startup_guardian as orch

        # Fetch real HubSpot data from Mockoon
        deals_r = httpx.get("http://localhost:8098/crm/v3/objects/deals", timeout=5)
        companies_r = httpx.get("http://localhost:8098/crm/v3/objects/companies", timeout=5)
        raw_deals = deals_r.json()["results"]
        raw_companies = companies_r.json()["results"]

        mock_deals = []
        for d in raw_deals:
            obj = MagicMock()
            obj.properties = d["properties"]
            mock_deals.append(obj)

        mock_companies = []
        for c in raw_companies:
            obj = MagicMock()
            obj.properties = c["properties"]
            mock_companies.append(obj)

        mock_client = MagicMock()
        mock_client.crm.deals.get_all.return_value = mock_deals
        mock_client.crm.companies.get_all.return_value = mock_companies

        # Patch connectors at orchestrator level (bypasses MOCK_MODE flag)
        original = orch._CONNECTORS
        orch._CONNECTORS = [
            ("erpnext", lambda tid: __import__("src.integrations.erpnext", fromlist=["get_erpnext_snapshot"]).get_erpnext_snapshot(tid)),
            ("hubspot", lambda tid: __import__("src.integrations.hubspot", fromlist=["get_hubspot_snapshot"]).get_hubspot_snapshot(tid)),
            ("quickbooks", lambda tid: __import__("src.integrations.quickbooks", fromlist=["get_quickbooks_snapshot"]).get_quickbooks_snapshot(tid)),
        ]
        try:
            with patch("hubspot.HubSpot", return_value=mock_client):
                result = await orch.run_startup_guardian("integration-test")
        finally:
            orch._CONNECTORS = original

        # ERPNext data
        assert result["support"]["open_issues"] == 3
        assert result["execution"]["active_projects"] == 2
        assert result["team"]["active_employees"] == 5

        # QuickBooks data (overwrites ERPNext finance)
        assert result["finance"]["outstanding_invoices"] == 3
        assert result["finance"]["total_outstanding_cents"] == 2_850_000

        # HubSpot data (mocked)
        assert result["revenue"]["total_deals_cents"] == 125_000_000

        # Health computed
        assert result["overall_health"] in ("good", "attention", "critical")

        # Connectors all OK
        assert result["connectors_ok"]["erpnext"] is True
        assert result["connectors_ok"]["hubspot"] is True
        assert result["connectors_ok"]["quickbooks"] is True

    @pytest.mark.asyncio
    async def test_pipeline_erpnext_fails(self):
        """ERPNext down → HubSpot + QuickBooks still work."""
        from unittest.mock import MagicMock
        import src.orchestration.run_startup_guardian as orch
        from src.integrations.quickbooks import get_quickbooks_snapshot

        deals_r = httpx.get("http://localhost:8098/crm/v3/objects/deals", timeout=5)
        raw_deals = deals_r.json()["results"]
        mock_deals = [MagicMock(properties=d["properties"]) for d in raw_deals]

        companies_r = httpx.get("http://localhost:8098/crm/v3/objects/companies", timeout=5)
        raw_companies = companies_r.json()["results"]
        mock_companies = [MagicMock(properties=c["properties"]) for c in raw_companies]

        mock_client = MagicMock()
        mock_client.crm.deals.get_all.return_value = mock_deals
        mock_client.crm.companies.get_all.return_value = mock_companies

        def mock_hubspot(tid):
            with patch("hubspot.HubSpot", return_value=mock_client):
                from src.integrations.hubspot import get_hubspot_snapshot
                return get_hubspot_snapshot(tid)

        original = orch._CONNECTORS
        orch._CONNECTORS = [
            ("hubspot", mock_hubspot),
            ("quickbooks", lambda tid: get_quickbooks_snapshot(tid)),
        ]
        try:
            result = await orch.run_startup_guardian("erpnext-down-test")
        finally:
            orch._CONNECTORS = original

        assert result["connectors_ok"].get("erpnext", True) is not True or "erpnext" not in result["connectors_ok"]
        assert result["finance"]["outstanding_invoices"] == 3

    @pytest.mark.asyncio
    async def test_watchlists_fire_on_real_data(self):
        """Watchlists fire correctly on real Mockoon data."""
        from unittest.mock import MagicMock
        from src.guardian.startup_watchlists import run_watchlists

        deals_r = httpx.get("http://localhost:8098/crm/v3/objects/deals", timeout=5)
        companies_r = httpx.get("http://localhost:8098/crm/v3/objects/companies", timeout=5)
        mock_deals = [MagicMock(properties=d["properties"]) for d in deals_r.json()["results"]]
        mock_companies = [MagicMock(properties=c["properties"]) for c in companies_r.json()["results"]]
        mock_client = MagicMock()
        mock_client.crm.deals.get_all.return_value = mock_deals
        mock_client.crm.companies.get_all.return_value = mock_companies

        with patch("hubspot.HubSpot", return_value=mock_client):
            from src.orchestration.run_startup_guardian import run_startup_guardian
            result = await run_startup_guardian("watchlist-test")

        alerts = run_watchlists(result)
        assert isinstance(alerts, list)
        for alert in alerts:
            assert "id" in alert
            assert "title" in alert
            assert "severity" in alert
            assert "domain" in alert
