"""Control Plane policy — thin wrapper over ``policy_bridge``.

No policy logic lives here: risk classification, approval gating,
and execution blocking delegate to ``src/mission/policy_bridge.py``.
No connector imports. No LLM calls.
"""

from __future__ import annotations

from typing import Any

from src.mission import policy_bridge


def classify(intent: Any, role_config: Any = None) -> str:
    """Return the effective risk tier for an intent (deferred to bridge)."""
    params = {"risk_tier": getattr(intent, "risk_tier", None)}
    params.update(dict(getattr(intent, "requested_parameters", {}) or {}))
    return policy_bridge.classify_risk(params, role_config)


def needs_approval(intent: Any, role_config: Any = None) -> bool:
    """HIGH/CRITICAL intents require human approval (deferred to bridge)."""
    params = dict(getattr(intent, "requested_parameters", {}) or {})
    return policy_bridge.requires_approval(params, role_config)


def is_blocked(intent: Any, role_config: Any = None) -> bool:
    """CRITICAL intents are blocked before any skill runs (bridge-owned)."""
    params = dict(getattr(intent, "requested_parameters", {}) or {})
    return policy_bridge.blocks_execution(params, role_config)
