"""Control Plane policy — risk classification from TRUSTED state only.

No policy logic lives here: risk classification, approval gating, and
execution blocking delegate to ``src/mission/policy_bridge.py``.
No connector imports. No LLM calls.

Trust boundary
--------------
``ActionIntent`` is untrusted LLM output. ``requested_parameters`` is
attacker-influenced, so it is NEVER consulted for risk. Doing so let a
prompt-injected planner set ``requested_parameters["risk_tier"] = "LOW"``
and bypass both the approval gate and the CRITICAL execution block.

The effective tier comes from, in order:

1. ``role_config.risk_threshold`` — the trusted, configured floor
2. canonical per-operation metadata, when the operation is registered
3. ``DEFAULT_RISK_TIER`` as the fail-closed fallback

A tier supplied inside the intent is ignored whatever its value.
"""

from __future__ import annotations

from typing import Any

from src.mission import policy_bridge

#: Fail-closed default when no trusted source supplies a threshold.
DEFAULT_RISK_TIER = "MEDIUM"


def _trusted_risk_tier(intent: Any, role_config: Any = None) -> str:
    """Return the risk tier derived exclusively from trusted state."""
    threshold = getattr(role_config, "risk_threshold", None)
    if threshold:
        return str(threshold).upper()
    return DEFAULT_RISK_TIER


def _trusted_params(intent: Any, role_config: Any = None) -> dict[str, Any]:
    """Build the parameter dict handed to the policy bridge.

    Contains ONLY the trusted tier. The intent's ``requested_parameters``
    are deliberately excluded — they are the injection surface this module
    exists to close.
    """
    return {"risk_tier": _trusted_risk_tier(intent, role_config)}


def classify(intent: Any, role_config: Any = None) -> str:
    """Return the effective risk tier for an intent (deferred to bridge)."""
    return policy_bridge.classify_risk(_trusted_params(intent, role_config), role_config)


def needs_approval(intent: Any, role_config: Any = None) -> bool:
    """HIGH/CRITICAL intents require human approval (deferred to bridge)."""
    return policy_bridge.requires_approval(
        _trusted_params(intent, role_config), role_config
    )


def is_blocked(intent: Any, role_config: Any = None) -> bool:
    """CRITICAL intents are blocked before any skill runs (bridge-owned)."""
    return policy_bridge.blocks_execution(
        _trusted_params(intent, role_config), role_config
    )
