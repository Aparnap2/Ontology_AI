"""
Anomaly detection thresholds — rule-based, NO LLM.
Dynamically configurable per-tenant via founder feedback learning.
"""

from typing import Dict, Any
import asyncio
from ..learning.feedback_consumer import get_agent_threshold

# Default thresholds (fallback values)
DEFAULT_ANOMALY_THRESHOLDS = {
    # Runway thresholds (days)
    "runway_drop": {
        "critical": 90,    # < 90 days → critical
        "warning": 180,    # < 180 days → warning
    },
    # MRR change thresholds (%)
    "mrr_drop": {
        "critical": -15.0,  # < -15% → critical
        "warning": -5.0,    # < -5% → warning
    },
    # Burn rate thresholds (ratio vs previous)
    "burn_spike": {
        "critical": 1.5,   # > 1.5x previous → critical
        "warning": 1.2,    # > 1.2x previous → warning
    },
    # Churn thresholds (count per month)
    "high_churn": {
        "critical": 3,     # >= 3 churned → critical
        "warning": 1,      # >= 1 churned → warning
    },
}

# Cache for tenant-specific thresholds
_threshold_cache: Dict[str, Dict[str, Any]] = {}


async def get_tenant_thresholds(tenant_id: str) -> Dict[str, Any]:
    """
    Get anomaly thresholds for a specific tenant, with learning-adjusted values.
    Falls back to defaults if no learned thresholds exist.
    """
    if tenant_id in _threshold_cache:
        return _threshold_cache[tenant_id]

    # Load dynamic thresholds from learning system
    thresholds = DEFAULT_ANOMALY_THRESHOLDS.copy()

    try:
        # Get learned threshold adjustments
        runway_critical = await get_agent_threshold("anomaly", "runway_drop_critical", tenant_id)
        runway_warning = await get_agent_threshold("anomaly", "runway_drop_warning", tenant_id)
        mrr_critical = await get_agent_threshold("anomaly", "mrr_drop_critical", tenant_id)
        mrr_warning = await get_agent_threshold("anomaly", "mrr_drop_warning", tenant_id)
        burn_critical = await get_agent_threshold("anomaly", "burn_spike_critical", tenant_id)
        burn_warning = await get_agent_threshold("anomaly", "burn_spike_warning", tenant_id)
        churn_critical = await get_agent_threshold("anomaly", "high_churn_critical", tenant_id)
        churn_warning = await get_agent_threshold("anomaly", "high_churn_warning", tenant_id)

        # Apply learned adjustments (these are normalized 0-1 values, map to appropriate ranges)
        if runway_critical is not None:
            thresholds["runway_drop"]["critical"] = 60 + (runway_critical * 60)  # 60-120 days
        if runway_warning is not None:
            thresholds["runway_drop"]["warning"] = 120 + (runway_warning * 120)  # 120-240 days

        if mrr_critical is not None:
            thresholds["mrr_drop"]["critical"] = -25.0 + (mrr_critical * 15.0)  # -25% to -10%
        if mrr_warning is not None:
            thresholds["mrr_drop"]["warning"] = -10.0 + (mrr_warning * 10.0)  # -10% to 0%

        if burn_critical is not None:
            thresholds["burn_spike"]["critical"] = 1.2 + (burn_critical * 0.8)  # 1.2x to 2.0x
        if burn_warning is not None:
            thresholds["burn_spike"]["warning"] = 1.0 + (burn_warning * 0.5)  # 1.0x to 1.5x

        if churn_critical is not None:
            thresholds["high_churn"]["critical"] = max(1, int(churn_critical * 6) + 1)  # 1-7 customers
        if churn_warning is not None:
            thresholds["high_churn"]["warning"] = max(0, int(churn_warning * 3))  # 0-3 customers

    except Exception as e:
        # If learning system fails, use defaults
        print(f"Warning: Could not load learned thresholds for tenant {tenant_id}: {e}")

    # Cache the thresholds
    _threshold_cache[tenant_id] = thresholds
    return thresholds


def get_anomaly_thresholds(tenant_id: str = None) -> Dict[str, Any]:
    """
    Synchronous wrapper for getting thresholds.
    For async contexts, use get_tenant_thresholds() directly.
    """
    if tenant_id is None:
        return DEFAULT_ANOMALY_THRESHOLDS

    # Try to get from cache first (for performance)
    if tenant_id in _threshold_cache:
        return _threshold_cache[tenant_id]

    # For sync contexts, return defaults and schedule async update
    asyncio.create_task(_update_cache_async(tenant_id))
    return DEFAULT_ANOMALY_THRESHOLDS


async def _update_cache_async(tenant_id: str):
    """Async helper to update threshold cache."""
    try:
        thresholds = await get_tenant_thresholds(tenant_id)
        _threshold_cache[tenant_id] = thresholds
    except Exception as e:
        print(f"Failed to update threshold cache for {tenant_id}: {e}")


# Backward compatibility
ANOMALY_THRESHOLDS = DEFAULT_ANOMALY_THRESHOLDS


def detect_anomaly(state: dict, tenant_id: str = None) -> dict:
    """
    Rule-based anomaly detection with tenant-specific learned thresholds. Returns:
    {
        "anomaly_detected": bool,
        "anomaly_type": str | None,
        "anomaly_severity": str | None,
        "threshold_used": float | None,
        "should_alert": bool,
    }
    """
    runway = state.get("runway_days", 999)
    mrr_change = state.get("mrr_change_pct", 0.0)
    burn = state.get("burn_rate_cents", 0)
    prev_burn = state.get("prev_burn_cents", burn)
    churned = state.get("churned_customers", 0)

    # Get tenant-specific thresholds
    thresholds = get_anomaly_thresholds(tenant_id)

    # Check runway
    if runway < thresholds["runway_drop"]["critical"]:
        return {
            "anomaly_detected": True,
            "anomaly_type": "runway_drop",
            "anomaly_severity": "critical",
            "threshold_used": thresholds["runway_drop"]["critical"],
            "should_alert": True,
        }
    elif runway < thresholds["runway_drop"]["warning"]:
        return {
            "anomaly_detected": True,
            "anomaly_type": "runway_drop",
            "anomaly_severity": "warning",
            "threshold_used": thresholds["runway_drop"]["warning"],
            "should_alert": True,
        }

    # Check MRR drop
    if mrr_change < thresholds["mrr_drop"]["critical"]:
        return {
            "anomaly_detected": True,
            "anomaly_type": "mrr_drop",
            "anomaly_severity": "critical",
            "threshold_used": thresholds["mrr_drop"]["critical"],
            "should_alert": True,
        }
    elif mrr_change < thresholds["mrr_drop"]["warning"]:
        return {
            "anomaly_detected": True,
            "anomaly_type": "mrr_drop",
            "anomaly_severity": "warning",
            "threshold_used": thresholds["mrr_drop"]["warning"],
            "should_alert": True,
        }

    # Check burn spike
    if prev_burn > 0:
        burn_ratio = burn / prev_burn
        if burn_ratio > thresholds["burn_spike"]["critical"]:
            return {
                "anomaly_detected": True,
                "anomaly_type": "burn_spike",
                "anomaly_severity": "critical",
                "threshold_used": thresholds["burn_spike"]["critical"],
                "should_alert": True,
            }
        elif burn_ratio > thresholds["burn_spike"]["warning"]:
            return {
                "anomaly_detected": True,
                "anomaly_type": "burn_spike",
                "anomaly_severity": "warning",
                "threshold_used": thresholds["burn_spike"]["warning"],
                "should_alert": True,
            }

    # Check high churn
    if churned >= thresholds["high_churn"]["critical"]:
        return {
            "anomaly_detected": True,
            "anomaly_type": "high_churn",
            "anomaly_severity": "critical",
            "threshold_used": thresholds["high_churn"]["critical"],
            "should_alert": True,
        }
    elif churned >= thresholds["high_churn"]["warning"]:
        return {
            "anomaly_detected": True,
            "anomaly_type": "high_churn",
            "anomaly_severity": "warning",
            "threshold_used": thresholds["high_churn"]["warning"],
            "should_alert": True,
        }

    # No anomaly detected
    return {
        "anomaly_detected": False,
        "anomaly_type": None,
        "anomaly_severity": None,
        "threshold_used": None,
        "should_alert": False,
    }


async def detect_anomaly_async(state: dict, tenant_id: str = None) -> dict:
    """
    Async version that uses learned tenant-specific thresholds.
    Preferred for new code that can handle async contexts.
    """
    runway = state.get("runway_days", 999)
    mrr_change = state.get("mrr_change_pct", 0.0)
    burn = state.get("burn_rate_cents", 0)
    prev_burn = state.get("prev_burn_cents", burn)
    churned = state.get("churned_customers", 0)

    # Get tenant-specific thresholds with learning
    thresholds = await get_tenant_thresholds(tenant_id) if tenant_id else DEFAULT_ANOMALY_THRESHOLDS

    # Check runway
    if runway < thresholds["runway_drop"]["critical"]:
        return {
            "anomaly_detected": True,
            "anomaly_type": "runway_drop",
            "anomaly_severity": "critical",
            "threshold_used": thresholds["runway_drop"]["critical"],
            "should_alert": True,
        }
    elif runway < thresholds["runway_drop"]["warning"]:
        return {
            "anomaly_detected": True,
            "anomaly_type": "runway_drop",
            "anomaly_severity": "warning",
            "threshold_used": thresholds["runway_drop"]["warning"],
            "should_alert": True,
        }

    # Check MRR drop
    if mrr_change < thresholds["mrr_drop"]["critical"]:
        return {
            "anomaly_detected": True,
            "anomaly_type": "mrr_drop",
            "anomaly_severity": "critical",
            "threshold_used": thresholds["mrr_drop"]["critical"],
            "should_alert": True,
        }
    elif mrr_change < thresholds["mrr_drop"]["warning"]:
        return {
            "anomaly_detected": True,
            "anomaly_type": "mrr_drop",
            "anomaly_severity": "warning",
            "threshold_used": thresholds["mrr_drop"]["warning"],
            "should_alert": True,
        }

    # Check burn spike
    if prev_burn > 0:
        burn_ratio = burn / prev_burn
        if burn_ratio > thresholds["burn_spike"]["critical"]:
            return {
                "anomaly_detected": True,
                "anomaly_type": "burn_spike",
                "anomaly_severity": "critical",
                "threshold_used": thresholds["burn_spike"]["critical"],
                "should_alert": True,
            }
        elif burn_ratio > thresholds["burn_spike"]["warning"]:
            return {
                "anomaly_detected": True,
                "anomaly_type": "burn_spike",
                "anomaly_severity": "warning",
                "threshold_used": thresholds["burn_spike"]["warning"],
                "should_alert": True,
            }

    # Check high churn
    if churned >= thresholds["high_churn"]["critical"]:
        return {
            "anomaly_detected": True,
            "anomaly_type": "high_churn",
            "anomaly_severity": "critical",
            "threshold_used": thresholds["high_churn"]["critical"],
            "should_alert": True,
        }
    elif churned >= thresholds["high_churn"]["warning"]:
        return {
            "anomaly_detected": True,
            "anomaly_type": "high_churn",
            "anomaly_severity": "warning",
            "threshold_used": thresholds["high_churn"]["warning"],
            "should_alert": True,
        }

    # No anomaly detected
    return {
        "anomaly_detected": False,
        "anomaly_type": None,
        "anomaly_severity": None,
        "threshold_used": None,
        "should_alert": False,
    }
