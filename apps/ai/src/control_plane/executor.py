"""Control Plane executor — the ONLY module that may trigger execution.

Thin wrapper over ``CapabilityOpRegistry`` (which owns the frozen
10-op set over the 4 connectors). No other control-plane module may
import connectors or the capability layer; all execution funnels here
so allowlists and governance stay in one choke point. No LLM calls.
"""

from __future__ import annotations

from typing import Any

from src.control_plane.contracts import AuthorizedAction
from src.mission.capability_ops import CapabilityOpRegistry


def execute(
    authorized: AuthorizedAction,
    role_caps: list[str] | None = None,
) -> dict[str, Any]:
    """Execute an authorized action via the capability-op registry."""
    return CapabilityOpRegistry.execute(
        authorized.operation,
        dict(authorized.requested_parameters or {}),
        authorized.tenant_id,
        role_caps=role_caps,
    )


def list_ops() -> list[str]:
    """Return the frozen op names (delegated to the registry)."""
    return CapabilityOpRegistry.list_ops()
