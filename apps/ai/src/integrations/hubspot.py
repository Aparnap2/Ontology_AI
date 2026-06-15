"""
HubSpot Integration Module for Startup Guardian.

Provides revenue and customer data extraction from HubSpot CRM.
Supports MOCK MODE for development/testing without real API credentials.

Environment Variables:
    HUBSPOT_ACCESS_TOKEN: HubSpot private app access token
"""
import os
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

MOCK_MODE: bool = not bool(os.getenv("HUBSPOT_ACCESS_TOKEN", "").strip())

_MOCK_DATA: Dict[str, Any] = {
    "revenue_total_deals_cents": 125000000,
    "revenue_won_deals_30d_cents": 50000000,
    "revenue_pipeline_deals_cents": 75000000,
    "revenue_active_customers": 3,
    "revenue_mrr_cents": None,
}


def _add_metadata(data: Dict[str, Any], source: str) -> Dict[str, Any]:
    result = data.copy()
    result["source"] = source
    result["fetched_at"] = datetime.utcnow().isoformat() + "Z"
    return result


def _parse_amount_cents(amount_str: Optional[str]) -> int:
    if not amount_str or not amount_str.strip():
        return 0
    try:
        return int(float(amount_str) * 100)
    except (ValueError, TypeError):
        return 0


def get_hubspot_snapshot(tenant_id: str) -> Dict[str, Any]:
    if MOCK_MODE:
        logger.info("[MOCK MODE] Returning seed HubSpot data for tenant %s", tenant_id)
        return _add_metadata(_MOCK_DATA, "hubspot_mock")

    token = os.getenv("HUBSPOT_ACCESS_TOKEN", "")
    if not token:
        logger.warning("HubSpot token not configured for tenant %s, using mock data", tenant_id)
        return _add_metadata(_MOCK_DATA, "hubspot_mock")

    try:
        from hubspot import HubSpot

        client = HubSpot(access_token=token)

        all_deals = client.crm.deals.get_all(
            properties=["dealname", "amount", "dealstage", "closedate", "createdate"]
        )
        all_companies = client.crm.companies.get_all(
            properties=["name", "domain", "industry"]
        )

        total_deals_cents = 0
        won_deals_30d_cents = 0
        pipeline_cents = 0
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

        for deal in all_deals:
            props = getattr(deal, "properties", {}) or {}
            amount_cents = _parse_amount_cents(props.get("amount"))
            dealstage = (props.get("dealstage", "") or "").lower()
            closedate_str = props.get("closedate", "") or ""

            total_deals_cents += amount_cents

            if "closedwon" in dealstage or dealstage == "closed_won":
                if closedate_str:
                    try:
                        closedate = datetime.fromisoformat(closedate_str.replace("Z", "+00:00"))
                        if closedate >= thirty_days_ago:
                            won_deals_30d_cents += amount_cents
                    except (ValueError, TypeError):
                        won_deals_30d_cents += amount_cents
                else:
                    won_deals_30d_cents += amount_cents

            if not any(s in dealstage for s in ["closedwon", "closed_won", "closedlost", "closed_lost"]):
                pipeline_cents += amount_cents

        active_customers = sum(1 for _ in all_companies)

        result = {
            "revenue_total_deals_cents": total_deals_cents,
            "revenue_won_deals_30d_cents": won_deals_30d_cents,
            "revenue_pipeline_deals_cents": pipeline_cents,
            "revenue_active_customers": active_customers,
            "revenue_mrr_cents": None,
        }

        return _add_metadata(result, "hubspot")

    except ImportError:
        logger.warning("hubspot-api-client package not installed, falling back to mock")
        return _add_metadata(_MOCK_DATA, "hubspot_mock")
    except Exception as e:
        logger.error("Error fetching HubSpot data for tenant %s: %s", tenant_id, e)
        return _add_metadata(_MOCK_DATA, "hubspot_mock")
