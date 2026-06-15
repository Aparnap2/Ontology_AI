"""Assembles FinanceState from ERPNext Sales Invoice + QuickBooks snapshot dict."""
from __future__ import annotations
import logging
from typing import Any, Dict
from src.states.schemas import FinanceState, FinancialHealth

logger = logging.getLogger(__name__)


def assemble_finance_state(raw: Dict[str, Any]) -> FinanceState:
    total_outstanding_cents = raw.get("finance_total_outstanding_cents", 0)
    total_overdue_cents = raw.get("finance_overdue_cents", 0)
    unpaid_cents = raw.get("finance_unpaid_cents")
    if unpaid_cents is None:
        unpaid_cents = raw.get("finance_unpaid_invoices_30d_cents", 0)

    if total_overdue_cents > 1_000_000:
        health = FinancialHealth.CRITICAL
    elif total_overdue_cents > 0:
        health = FinancialHealth.WARNING
    else:
        health = FinancialHealth.HEALTHY

    return FinanceState(
        outstanding_invoices=raw.get("finance_outstanding_invoices", 0),
        total_outstanding_cents=total_outstanding_cents,
        overdue_invoices=raw.get("finance_overdue_invoices", 0),
        total_overdue_cents=total_overdue_cents,
        unpaid_invoices_30d_cents=unpaid_cents,
        paid_invoices_30d_cents=raw.get("finance_paid_invoices_30d_cents", 0),
        days_sales_outstanding=raw.get("finance_days_sales_outstanding"),
        health=health,
    )
