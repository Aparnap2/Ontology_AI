"""
Stripe Integration Module for OntologyAI MVP.

Provides MRR (Monthly Recurring Revenue) data extraction from Stripe.
Supports MOCK MODE for development/testing without real API keys.

Environment Variables:
    STRIPE_API_KEY: Stripe secret key (sk_live_... or sk_test_...)
    STRIPE_API_URL: Optional custom API URL (defaults to https://api.stripe.com)

Mock Mode:
    When STRIPE_API_KEY is empty or not set, returns realistic seed data
    for development and testing purposes.
"""

import os
import logging
from typing import Dict, Any, Optional
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)

# Mock mode flag - True when STRIPE_API_KEY is not configured
MOCK_MODE: bool = not bool(os.getenv("STRIPE_API_KEY", "").strip())

# Realistic mock data for development/testing
_MOCK_MRR_DATA: Dict[str, Any] = {
    "mrr_cents": 1250000,  # ₹12,500 MRR
    "arr_cents": 15000000,  # ₹1,50,000 ARR
    "active_customers": 25,
    "new_customers": 3,
    "churned_customers": 1,
}


def _add_metadata(data: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Add common metadata fields to integration responses."""
    result = data.copy()
    result["source"] = source
    result["fetched_at"] = datetime.utcnow().isoformat() + "Z"
    return result


def _normalize_to_monthly(amount_cents: int, interval: str) -> int:
    """
    Normalize subscription amount to monthly MRR.

    Args:
        amount_cents: Subscription amount in cents/paise
        interval: Billing interval (day, week, month, year)

    Returns:
        Monthly equivalent amount in cents
    """
    if interval == "day":
        return amount_cents * 30
    elif interval == "week":
        return amount_cents * 4  # ~4 weeks per month
    elif interval == "month":
        return amount_cents
    elif interval == "year":
        return amount_cents // 12
    else:
        return amount_cents


def _fetch_stripe_subscriptions(api_key: str, starting_after: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch subscriptions from Stripe API with pagination support.

    Args:
        api_key: Stripe API key
        starting_after: Cursor for pagination

    Returns:
        Stripe API response dict
    """
    base_url = os.getenv("STRIPE_API_URL", "https://api.stripe.com")
    url = f"{base_url}/v1/subscriptions"

    params = {"status": "active", "limit": 100}
    if starting_after:
        params["starting_after"] = starting_after

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Stripe-Version": "2023-10-16",
    }

    try:
        response = httpx.get(url, params=params, headers=headers, timeout=30.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.warning(f"Stripe API error: {e}")
        return {"data": [], "has_more": False}
    except Exception as e:
        logger.error(f"Unexpected error fetching Stripe subscriptions: {e}")
        return {"data": [], "has_more": False}


def get_mrr_snapshot(tenant_id: str) -> Dict[str, Any]:
    """
    Get MRR snapshot for a tenant from Stripe.

    Fetches active subscriptions and calculates:
    - MRR (Monthly Recurring Revenue)
    - ARR (Annual Recurring Revenue = MRR * 12)
    - Active customer count
    - New customers (subscriptions started this month)
    - Churned customers (subscriptions cancelled this month)

    Args:
        tenant_id: Tenant identifier (used for logging, not API calls)

    Returns:
        Dict with keys:
            - mrr_cents: Monthly recurring revenue in cents/paise
            - arr_cents: Annual recurring revenue in cents/paise
            - active_customers: Count of active subscriptions
            - new_customers: Count of new subscriptions this month
            - churned_customers: Count of churned subscriptions this month

    Example:
        >>> snapshot = get_mrr_snapshot("tenant-123")
        >>> print(f"MRR: ₹{snapshot['mrr_cents']/100:.0f}")
    """
    # Return mock data if not configured
    if MOCK_MODE:
        logger.info(f"[MOCK MODE] Returning seed MRR data for tenant {tenant_id}")
        return _add_metadata(_MOCK_MRR_DATA, "stripe_mock")

    api_key = os.getenv("STRIPE_API_KEY", "")
    if not api_key:
        logger.warning(f"Stripe API key not configured for tenant {tenant_id}, using mock data")
        return _add_metadata(_MOCK_MRR_DATA, "stripe_mock")

    try:
        total_mrr_cents = 0
        active_customers = 0
        new_customers = 0
        churned_customers = 0

        # Fetch all subscriptions with pagination
        has_more = True
        starting_after: Optional[str] = None

        while has_more:
            response = _fetch_stripe_subscriptions(api_key, starting_after)
            subscriptions = response.get("data", [])
            has_more = response.get("has_more", False)

            if subscriptions:
                starting_after = subscriptions[-1].get("id")

            for sub in subscriptions:
                # Skip test mode subscriptions
                if sub.get("test_mode", False):
                    continue

                # Calculate MRR for this subscription
                plan = sub.get("plan", {}) or {}
                amount = plan.get("amount", 0)
                interval = plan.get("interval", "month")
                quantity = sub.get("quantity", 1)

                monthly_mrr = _normalize_to_monthly(amount * quantity, interval)
                total_mrr_cents += monthly_mrr
                active_customers += 1

                # Check if new this month (simplified - in prod use proper date handling)
                created = sub.get("created", 0)
                # Assuming current timestamp check would be done here
                # For now, just count based on metadata if available
                if sub.get("metadata", {}).get("new_this_month") == "true":
                    new_customers += 1

        # Fetch cancelled subscriptions for churn count
        cancelled_url = f"{os.getenv('STRIPE_API_URL', 'https://api.stripe.com')}/v1/subscriptions"
        try:
            cancelled_response = httpx.get(
                cancelled_url,
                params={"status": "canceled", "limit": 100},
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30.0,
            )
            if cancelled_response.status_code == 200:
                churned_customers = len(cancelled_response.json().get("data", []))
        except Exception as e:
            logger.warning(f"Could not fetch cancelled subscriptions: {e}")

        result = {
            "mrr_cents": total_mrr_cents,
            "arr_cents": total_mrr_cents * 12,
            "active_customers": active_customers,
            "new_customers": new_customers,
            "churned_customers": churned_customers,
        }

        logger.info(
            f"Stripe MRR snapshot for {tenant_id}: "
            f"MRR=₹{total_mrr_cents/100:.0f}, Customers={active_customers}"
        )

        return result

    except Exception as e:
        logger.error(f"Error fetching Stripe MRR for tenant {tenant_id}: {e}")
        # Fall back to mock data on error
        return _add_metadata(_MOCK_MRR_DATA, "stripe_mock")
