"""Control Plane — thin composition over existing machinery (scaffold).

Only :mod:`executor` may trigger connector execution (via
``CapabilityOpRegistry``); every other module wraps governance,
policy, signals, verify, or audit. No direct connector imports.

Lazy exports (PEP 562): importing ``src.control_plane.contracts``
must NOT pull executor/authorization (which reach governance and
would circular-import ``src.ontology.action_types``).
"""

from __future__ import annotations

from typing import Any

_LAZY: dict[str, str] = {
    "ActionIntent": ".contracts",
    "AuthorizedAction": ".contracts",
    "PolicyDecision": ".contracts",
    "RiskTier": ".contracts",
    "AUDIT_LOG": ".audit",
    "append_event": ".audit",
    "list_events": ".audit",
    "authorize": ".authorization",
    "await_approval": ".approval",
    "request_approval": ".approval",
    "resolve_approval": ".approval",
    "execute": ".executor",
    "list_ops": ".executor",
    "SeenSet": ".idempotency",
    "build_idempotency_key": ".idempotency",
    "submit_intent": ".ingress",
    "classify": ".policy",
    "is_blocked": ".policy",
    "needs_approval": ".policy",
    "outcome_event": ".verification",
    "verify_execution": ".verification",
}

__all__ = sorted(_LAZY)


def __getattr__(name: str) -> Any:
    if name not in _LAZY:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(_LAZY[name], __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted([*globals(), *__all__])
