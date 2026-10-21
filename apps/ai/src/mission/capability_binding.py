"""Capability binding — runtime-bound capability resolution (Phase E P0).

Selects the backing implementation for capability ops by runtime binding:

- ``test``: in-memory deterministic doubles (historical behavior; ``mock_mode``).
- ``demo``: real HTTP against the stateful local Mockoon connectors.
- ``prod``: real SDK/HTTP where configured; raises :class:`NotConfigured`
  until credentials exist — never a silent in-memory fallback.

Mission/agent code never observes the choice: the ONLY branch lives in
``capability_ops._resolve_capability`` via this module. Precedence:
``ONTOLOGY_CAPABILITY_BINDING`` env > ``config/runtime.yaml``
``capability_binding`` > default ``"test"`` (current behavior preserved).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

CapabilityBindingName = Literal["test", "demo", "prod"]

VALID_BINDINGS: tuple[str, ...] = ("test", "demo", "prod")
DEFAULT_BINDING = "test"
ENV_VAR = "ONTOLOGY_CAPABILITY_BINDING"
YAML_KEY = "capability_binding"


class CapabilityBindingError(Exception):
    """Base error for the capability binding layer."""


class NotConfigured(CapabilityBindingError):
    """Raised when a demo/prod binding cannot be satisfied.

    Never silently falls back to in-memory: the caller gets a clear,
    actionable message naming exactly what is missing (connector mock,
    credentials, base URL).
    """


_cached_binding: str | None = None


def reset_binding_cache() -> None:
    """Clear the cached binding (tests only; production reads once)."""
    global _cached_binding
    _cached_binding = None


def _binding_from_yaml() -> str | None:
    """Read the binding from ``config/runtime.yaml``; None when absent."""
    candidates = [
        Path.cwd() / "config" / "runtime.yaml",
        Path(__file__).resolve().parents[2] / "config" / "runtime.yaml",
    ]
    path: Path | None = next((c for c in candidates if c.exists()), None)
    if path is None:
        return None
    try:
        import yaml  # local import: pyyaml only needed for this small loader
    except ImportError:
        logger.warning("pyyaml unavailable — ignoring %s binding key", path)
        return None
    try:
        text = os.path.expandvars(path.read_text(encoding="utf-8"))
        data = yaml.safe_load(text) or {}
    except Exception as exc:  # noqa: BLE001 — fail closed with a clear error
        raise CapabilityBindingError(f"cannot parse {path}: {exc}") from exc
    value = data.get(YAML_KEY)
    return str(value).strip() if value is not None else None


def get_capability_binding(*, refresh: bool = False) -> str:
    """Return the active capability binding (``test`` | ``demo`` | ``prod``).

    Precedence: ``ONTOLOGY_CAPABILITY_BINDING`` env > ``config/runtime.yaml``
    ``capability_binding`` > default ``"test"``. An explicit-but-unknown
    value fails closed with :class:`CapabilityBindingError` (never a silent
    downgrade to in-memory).
    """
    global _cached_binding
    if _cached_binding is not None and not refresh:
        return _cached_binding
    raw = os.getenv(ENV_VAR)
    source = f"env {ENV_VAR}"
    if not raw:
        raw = _binding_from_yaml()
        source = "config/runtime.yaml"
    binding = (raw or DEFAULT_BINDING).strip()
    if binding not in VALID_BINDINGS:
        raise CapabilityBindingError(
            f"invalid capability binding {binding!r} from {source}; "
            f"expected one of {list(VALID_BINDINGS)}"
        )
    _cached_binding = binding
    return binding
