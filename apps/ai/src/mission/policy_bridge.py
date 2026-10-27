"""Policy bridge — deterministic Level-2 risk classification for the runtime.

Maps a step's ``risk_tier`` (or the role's ``risk_threshold`` fallback) to the
approval gate. HIGH and CRITICAL always require human approval; LOW/MEDIUM do
not. The runtime additionally BLOCKS CRITICAL steps before any skill runs.

The bridge also wires the existing :class:`DefaultPolicyRuntime` (evaluate →
permit → record) so the employee loop can consult the policy engine.
"""
from __future__ import annotations

from typing import Any

from src.policy.runtime import DefaultPolicyRuntime

APPROVAL_TIERS = {"HIGH", "CRITICAL"}
BLOCK_TIERS = {"CRITICAL"}


def classify_risk(params: dict[str, Any], role_config: Any) -> str:
    """Return the effective risk tier: explicit risk_tier, else role threshold."""
    risk_tier = params.get("risk_tier") or getattr(role_config, "risk_threshold", "MEDIUM")
    return str(risk_tier).upper()


def requires_approval(params: dict[str, Any], role_config: Any) -> bool:
    """HIGH and CRITICAL always require approval; LOW/MEDIUM do not."""
    return classify_risk(params, role_config) in APPROVAL_TIERS


def blocks_execution(params: dict[str, Any], role_config: Any) -> bool:
    """CRITICAL steps are blocked before any skill runs."""
    return classify_risk(params, role_config) in BLOCK_TIERS


def get_policy_runtime() -> DefaultPolicyRuntime:
    """Return the default policy runtime (evaluate → permit → record)."""
    return DefaultPolicyRuntime()