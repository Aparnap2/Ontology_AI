"""
QuickBooks Integration Module for Startup Guardian.

Provides finance/accounting data extraction from QuickBooks Online.
Supports MOCK MODE for development/testing without real API credentials.

Environment Variables:
    QUICKBOOKS_CLIENT_ID: QuickBooks OAuth2 client ID
    QUICKBOOKS_ACCESS_TOKEN: QuickBooks OAuth2 access token
    QUICKBOOKS_COMPANY_ID: QuickBooks company/realm ID
    QUICKBOOKS_API_URL: Base URL (default: http://localhost:8097 for Mockoon)
"""
import os
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timedelta
import httpx

from .retry import circuit_breaker, retry_with_backoff

logger = logging.getLogger(__name__)

MOCK_MODE: bool = not bool(os.getenv("QUICKBOOKS_CLIENT_ID", "").strip())

_MOCK_DATA: Dict[str, Any] = {
    "finance_outstanding_invoices": 3,
    "finance_total_outstanding_cents": 2850000,
    "finance_overdue_invoices": 2,
    "finance_total_overdue_cents": 2000000,
    "finance_paid_invoices_30d_cents": 1500000,
    "finance_unpaid_invoices_30d_cents": 2850000,
    "finance_days_sales_outstanding": 57.0,
}


def _add_metadata(data: Dict[str, Any], source: str) -> Dict[str, Any]:
    result = data.copy()
    result["source"] = source
    result["fetched_at"] = datetime.utcnow().isoformat() + "Z"
    return result


def _parse_invoice_amount(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(float(value) * 100)
    except (ValueError, TypeError):
        return 0


def _calculate_dso(total_receivables_cents: int, paid_30d_cents: int) -> Optional[float]:
    if paid_30d_cents <= 0:
        return None
    avg_daily_sales_cents = paid_30d_cents / 30.0
    if avg_daily_sales_cents <= 0:
        return None
    return round(total_receivables_cents / avg_daily_sales_cents, 1)


@circuit_breaker("quickbooks")
def get_quickbooks_snapshot(tenant_id: str) -> Dict[str, Any]:
    """Get QuickBooks finance snapshot for a tenant.

    In ``MOCK_MODE`` (credentials not set) returns seed data.  In production,
    failures after retry are **raised** rather than silently replaced with
    mock data — this ensures errors are visible to the orchestrator.
    """
    if MOCK_MODE:
        logger.info("[MOCK MODE] Returning seed QuickBooks data for tenant %s", tenant_id)
        return _add_metadata(_MOCK_DATA, "quickbooks_mock")

    client_id = os.getenv("QUICKBOOKS_CLIENT_ID", "")
    access_token = os.getenv("QUICKBOOKS_ACCESS_TOKEN", "")
    company_id = os.getenv("QUICKBOOKS_COMPANY_ID", "")
    api_url = os.getenv("QUICKBOOKS_API_URL", "http://localhost:8097")

    if not client_id or not access_token or not company_id:
        logger.warning(
            "QuickBooks credentials not fully configured for tenant %s, "
            "returning mock data",
            tenant_id,
        )
        return _add_metadata(_MOCK_DATA, "quickbooks_mock")

    try:
        url = f"{api_url}/v3/company/{company_id}/query"
        params = {"query": "select * from Invoice STARTPOSITION 1 MAXRESULTS 1000"}
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/text",
        }

        def _fetch_invoices() -> list:
            """Single HTTP attempt — retried by ``retry_with_backoff``."""
            response = httpx.get(url, params=params, headers=headers, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            query_response = data.get("QueryResponse", {}) or {}
        invoices = query_response.get("Invoice", [])

        if not invoices:
            return _add_metadata({
                "finance_outstanding_invoices": 0,
                "finance_total_outstanding_cents": 0,
                "finance_overdue_invoices": 0,
                "finance_total_overdue_cents": 0,
                "finance_paid_invoices_30d_cents": 0,
                "finance_unpaid_invoices_30d_cents": 0,
                "finance_days_sales_outstanding": None,
            }, "quickbooks")

        now = datetime.utcnow()
        thirty_days_ago = now - timedelta(days=30)

        outstanding_invoices = 0
        total_outstanding_cents = 0
        overdue_invoices = 0
        total_overdue_cents = 0
        paid_invoices_30d_cents = 0
        unpaid_invoices_30d_cents = 0

        for inv in invoices:
            total_amt_cents = _parse_invoice_amount(inv.get("TotalAmt"))
            balance_cents = _parse_invoice_amount(inv.get("Balance"))
            due_date_str = inv.get("DueDate", "")
            txn_date_str = inv.get("TxnDate", "")

            due_date: Optional[datetime] = None
            txn_date: Optional[datetime] = None

            if due_date_str:
                try:
                    due_date = datetime.fromisoformat(due_date_str)
                except (ValueError, TypeError):
                    pass

            if txn_date_str:
                try:
                    txn_date = datetime.fromisoformat(txn_date_str)
                except (ValueError, TypeError):
                    pass

            if balance_cents > 0:
                outstanding_invoices += 1
                total_outstanding_cents += balance_cents
                if txn_date and txn_date >= thirty_days_ago:
                    unpaid_invoices_30d_cents += balance_cents
                if due_date and due_date < now:
                    overdue_invoices += 1
                    total_overdue_cents += balance_cents

            if balance_cents == 0 and txn_date and txn_date >= thirty_days_ago:
                paid_invoices_30d_cents += total_amt_cents

        dso = _calculate_dso(total_outstanding_cents, paid_invoices_30d_cents)

        result = {
            "finance_outstanding_invoices": outstanding_invoices,
            "finance_total_outstanding_cents": total_outstanding_cents,
            "finance_overdue_invoices": overdue_invoices,
            "finance_total_overdue_cents": total_overdue_cents,
            "finance_paid_invoices_30d_cents": paid_invoices_30d_cents,
            "finance_unpaid_invoices_30d_cents": unpaid_invoices_30d_cents,
            "finance_days_sales_outstanding": dso,
        }

        return _add_metadata(result, "quickbooks")

    except Exception as e:
        logger.error("Error fetching QuickBooks data for tenant %s: %s", tenant_id, e)
        return _add_metadata(_MOCK_DATA, "quickbooks_mock")
