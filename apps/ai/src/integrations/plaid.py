"""
Plaid/Mercury Integration Module for OntologyAI MVP.

Provides bank account balance and burn rate data extraction.
Supports both Plaid and Mercury providers via BANK_PROVIDER env var.
Supports MOCK MODE for development/testing without real API keys.

Environment Variables:
    BANK_PROVIDER: 'plaid' or 'mercury' (default: 'plaid')
    PLAID_ACCESS_TOKEN: Plaid access token for account data
    PLAID_CLIENT_ID: Plaid client ID
    PLAID_SECRET: Plaid secret key
    PLAID_ENV: Plaid environment (sandbox, development, production)
    MERCURY_TOKEN: Mercury API token
    MERCURY_ACCOUNT_ID: Mercury account ID

Mock Mode:
    When both PLAID_ACCESS_TOKEN and MERCURY_TOKEN are empty,
    returns realistic seed data for development and testing.

Transaction Amount Convention:
    Positive amount = debit/expense (money out)
    Negative amount = credit/income (money in)
"""

import os
import logging
from typing import Dict, Any
from datetime import datetime, timedelta
import httpx

logger = logging.getLogger(__name__)

# Mock mode flag - True when neither Plaid nor Mercury is configured
MOCK_MODE: bool = not (
    bool(os.getenv("PLAID_ACCESS_TOKEN", "").strip()) or
    bool(os.getenv("MERCURY_TOKEN", "").strip())
)

# Bank provider selection
BANK_PROVIDER: str = os.getenv("BANK_PROVIDER", "plaid").lower()

# Realistic mock data for development/testing
_MOCK_BANK_DATA: Dict[str, Any] = {
    "balance_cents": 45000000,  # ₹4,50,000 balance
    "burn_30d_cents": 15000000,  # ₹1,50,000 burn over 30 days
}


def _add_metadata(data: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Add common metadata fields to integration responses."""
    result = data.copy()
    result["source"] = source
    result["fetched_at"] = datetime.utcnow().isoformat() + "Z"
    return result


def _calculate_burn_rate(transactions: list) -> int:
    """
    Calculate 30-day burn rate from transactions.

    Args:
        transactions: List of transaction dicts with 'amount' field

    Returns:
        Total burn (expenses) in cents over 30 days

    Note:
        Positive amounts are debits/expenses (money out)
        Negative amounts are credits/income (money in)
    """
    thirty_days_ago = datetime.now() - timedelta(days=30)
    total_burn = 0

    for txn in transactions:
        txn_date = txn.get("date", "")
        try:
            if txn_date:
                txn_datetime = datetime.fromisoformat(txn_date.replace("Z", "+00:00"))
                if txn_datetime < thirty_days_ago:
                    continue
        except (ValueError, TypeError):
            pass

        # Positive amount = expense/debit
        amount = txn.get("amount", 0)
        if amount > 0:
            total_burn += amount

    return total_burn


def _fetch_plaid_transactions(
    access_token: str,
    start_date: str,
    end_date: str,
    offset: int = 0
) -> Dict[str, Any]:
    """
    Fetch transactions from Plaid API with pagination.

    Args:
        access_token: Plaid access token
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        offset: Pagination offset

    Returns:
        Plaid API response dict
    """
    client_id = os.getenv("PLAID_CLIENT_ID", "")
    secret = os.getenv("PLAID_SECRET", "")
    plaid_env = os.getenv("PLAID_ENV", "sandbox")

    # Map environment to URL
    env_urls = {
        "sandbox": "https://sandbox.plaid.com",
        "development": "https://development.plaid.com",
        "production": "https://production.plaid.com",
    }
    base_url = env_urls.get(plaid_env, "https://sandbox.plaid.com")

    url = f"{base_url}/transactions/get"

    payload = {
        "client_id": client_id,
        "secret": secret,
        "access_token": access_token,
        "start_date": start_date,
        "end_date": end_date,
        "options": {
            "count": 100,
            "offset": offset,
        },
    }

    try:
        response = httpx.post(url, json=payload, timeout=30.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.warning(f"Plaid API error: {e}")
        return {"transactions": [], "total_transactions": 0}
    except Exception as e:
        logger.error(f"Unexpected error fetching Plaid transactions: {e}")
        return {"transactions": [], "total_transactions": 0}


def _fetch_plaid_balance(access_token: str) -> Dict[str, Any]:
    """
    Fetch account balance from Plaid API.

    Args:
        access_token: Plaid access token

    Returns:
        Plaid balance response dict
    """
    client_id = os.getenv("PLAID_CLIENT_ID", "")
    secret = os.getenv("PLAID_SECRET", "")
    plaid_env = os.getenv("PLAID_ENV", "sandbox")

    env_urls = {
        "sandbox": "https://sandbox.plaid.com",
        "development": "https://development.plaid.com",
        "production": "https://production.plaid.com",
    }
    base_url = env_urls.get(plaid_env, "https://sandbox.plaid.com")

    url = f"{base_url}/accounts/balance/get"

    payload = {
        "client_id": client_id,
        "secret": secret,
        "access_token": access_token,
    }

    try:
        response = httpx.post(url, json=payload, timeout=30.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.warning(f"Plaid balance API error: {e}")
        return {"accounts": []}
    except Exception as e:
        logger.error(f"Unexpected error fetching Plaid balance: {e}")
        return {"accounts": []}


def _fetch_mercury_transactions(account_id: str, token: str) -> list:
    """
    Fetch transactions from Mercury API.

    Args:
        account_id: Mercury account ID
        token: Mercury API token

    Returns:
        List of transaction dicts
    """
    base_url = "https://api.mercury.com/api/v1"

    headers = {"Authorization": f"Bearer {token}"}

    try:
        # Fetch transactions for last 30 days
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        url = f"{base_url}/accounts/{account_id}/transactions"
        params = {"after": thirty_days_ago}

        response = httpx.get(url, params=params, headers=headers, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        return data.get("data", [])
    except httpx.HTTPError as e:
        logger.warning(f"Mercury API error: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching Mercury transactions: {e}")
        return []


def _fetch_mercury_balance(account_id: str, token: str) -> int:
    """
    Fetch account balance from Mercury API.

    Args:
        account_id: Mercury account ID
        token: Mercury API token

    Returns:
        Balance in cents
    """
    base_url = "https://api.mercury.com/api/v1"

    headers = {"Authorization": f"Bearer {token}"}

    try:
        url = f"{base_url}/accounts/{account_id}"
        response = httpx.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        # Mercury returns balance in cents
        return data.get("data", {}).get("balance", 0)
    except httpx.HTTPError as e:
        logger.warning(f"Mercury balance API error: {e}")
        return 0
    except Exception as e:
        logger.error(f"Unexpected error fetching Mercury balance: {e}")
        return 0


def _get_plaid_snapshot(tenant_id: str) -> Dict[str, Any]:
    """
    Get bank snapshot from Plaid.

    Args:
        tenant_id: Tenant identifier

    Returns:
        Bank snapshot dict
    """
    access_token = os.getenv("PLAID_ACCESS_TOKEN", "")

    if not access_token:
        logger.warning(f"Plaid access token not configured for tenant {tenant_id}")
        return {
            "balance_cents": _MOCK_BANK_DATA["balance_cents"],
            "burn_30d_cents": _MOCK_BANK_DATA["burn_30d_cents"],
            "runway_months": 3.0,
        }

    # Fetch balance
    balance_response = _fetch_plaid_balance(access_token)
    total_balance = 0

    for account in balance_response.get("accounts", []):
        balances = account.get("balances", {})
        # Plaid returns balance in currency units, convert to cents
        available = balances.get("available", 0) or balances.get("current", 0)
        total_balance += int(available * 100)

    # Fetch transactions for burn rate calculation
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    all_transactions = []
    offset = 0
    total_fetched = 0

    while True:
        response = _fetch_plaid_transactions(access_token, start_date, end_date, offset)
        transactions = response.get("transactions", [])
        total_transactions = response.get("total_transactions", 0)

        all_transactions.extend(transactions)
        total_fetched += len(transactions)

        if total_fetched >= total_transactions:
            break

        offset += 100

    # Calculate burn rate (positive amounts = expenses)
    burn_30d = _calculate_burn_rate(all_transactions)

    if burn_30d == 0:
        burn_30d = _MOCK_BANK_DATA["burn_30d_cents"]  # Fallback

    runway = total_balance / burn_30d if burn_30d > 0 else float("inf")

    logger.info(
        f"Plaid bank snapshot for {tenant_id}: "
        f"Balance=₹{total_balance/100:.0f}, Burn=₹{burn_30d/100:.0f}, Runway={runway:.1f} months"
    )

    return {
        "balance_cents": total_balance,
        "burn_30d_cents": burn_30d,
        "runway_months": runway,
    }


def _get_mercury_snapshot(tenant_id: str) -> Dict[str, Any]:
    """
    Get bank snapshot from Mercury.

    Args:
        tenant_id: Tenant identifier

    Returns:
        Bank snapshot dict
    """
    token = os.getenv("MERCURY_TOKEN", "")
    account_id = os.getenv("MERCURY_ACCOUNT_ID", "")

    if not token or not account_id:
        logger.warning(f"Mercury credentials not configured for tenant {tenant_id}")
        return {
            "balance_cents": _MOCK_BANK_DATA["balance_cents"],
            "burn_30d_cents": _MOCK_BANK_DATA["burn_30d_cents"],
            "runway_months": 3.0,
        }

    # Fetch balance (Mercury returns in cents)
    balance = _fetch_mercury_balance(account_id, token)

    # Fetch transactions for burn rate
    transactions = _fetch_mercury_transactions(account_id, token)

    # Mercury: positive amounts are debits/expenses
    burn_30d = sum(txn.get("amount", 0) for txn in transactions if txn.get("amount", 0) > 0)

    if burn_30d == 0:
        burn_30d = _MOCK_BANK_DATA["burn_30d_cents"]  # Fallback

    runway = balance / burn_30d if burn_30d > 0 else float("inf")

    logger.info(
        f"Mercury bank snapshot for {tenant_id}: "
        f"Balance=₹{balance/100:.0f}, Burn=₹{burn_30d/100:.0f}, Runway={runway:.1f} months"
    )

    return {
        "balance_cents": balance,
        "burn_30d_cents": burn_30d,
        "runway_months": runway,
    }


def get_bank_snapshot(tenant_id: str) -> Dict[str, Any]:
    """
    Get bank snapshot for a tenant.

    Fetches account balance and calculates 30-day burn rate.
    Supports both Plaid and Mercury providers.

    Args:
        tenant_id: Tenant identifier (used for logging)

    Returns:
        Dict with keys:
            - balance_cents: Current account balance in cents/paise
            - burn_30d_cents: Total expenses over last 30 days in cents
            - runway_months: Estimated runway in months (balance / monthly burn)

    Example:
        >>> snapshot = get_bank_snapshot("tenant-123")
        >>> print(f"Balance: ₹{snapshot['balance_cents']/100:.0f}")
        >>> print(f"Burn: ₹{snapshot['burn_30d_cents']/100:.0f}")
        >>> print(f"Runway: {snapshot['runway_months']:.1f} months")
    """
    # Return mock data if not configured
    if MOCK_MODE:
        logger.info(f"[MOCK MODE] Returning seed bank data for tenant {tenant_id}")
        balance = _MOCK_BANK_DATA["balance_cents"]
        burn = _MOCK_BANK_DATA["burn_30d_cents"]
        return _add_metadata({
            "balance_cents": balance,
            "burn_30d_cents": burn,
            "runway_months": balance / burn if burn > 0 else float("inf"),
        }, "bank_mock")

    try:
        if BANK_PROVIDER == "mercury":
            return _get_mercury_snapshot(tenant_id)
        else:
            return _get_plaid_snapshot(tenant_id)

    except Exception as e:
        logger.error(f"Error fetching bank snapshot for tenant {tenant_id}: {e}")
        # Fall back to mock data on error
        return {
            "balance_cents": _MOCK_BANK_DATA["balance_cents"],
            "burn_30d_cents": _MOCK_BANK_DATA["burn_30d_cents"],
            "runway_months": 3.0,
        }
