"""OntologyAI V4.2 — MissionState → Ontology Adapter (Task 2).

Maps the flat :class:`MissionState` dict (the shared context object that all
agents read/write) into the six canonical typed Object Type lists defined in
:mod:`src.ontology.object_types`.

Design goals
------------
* **Tolerant** — unknown / legacy / malformed keys are ignored, never raise.
* **Typed** — every value returned is a validated Pydantic model instance
  (``extra="forbid"`` + ``strict=True`` models), so downstream governance can
  trust the shape.
* **Non-destructive** — the input ``MissionState`` is never mutated and the
  adapter never raises on partial / legacy payloads.

Mapping rules
-------------
For each Object Type the adapter first looks for a recognized *list-valued*
source key (e.g. ``customers`` → ``Customer``). Recognized keys are checked
in priority order; the first list found wins.

``RevenueMetric`` additionally supports *derivation* from the flat finance
scalar keys that the real ``MissionState`` actually carries (``mrr``,
``burn_rate`` / ``burn``, ``runway_days`` / ``runway``). This lets a plain
``MissionState`` produce a typed revenue snapshot even when no explicit
``revenue_metrics`` list is present.

Unknown keys (anything not in the recognized set) are silently ignored.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ValidationError

from src.ontology.object_types import (
    OBJECT_TYPES,
    Customer,
    Deal,
    Incident,
    Message,
    PlannedAction,
    RevenueMetric,
)

log = logging.getLogger(__name__)

# Recognized source keys per Object Type, checked in priority order.
# The first list-valued key found for a type is used.
_LIST_KEYS: dict[str, tuple[str, ...]] = {
    "Customer": ("customers", "customer", "customer_list"),
    "Deal": ("deals", "deal", "deal_list", "pipeline"),
    "RevenueMetric": ("revenue_metrics", "revenue_metric", "revenue"),
    "Incident": ("incidents", "incident", "incident_list"),
    "Message": ("messages", "message", "message_list"),
    "PlannedAction": ("planned_actions", "planned_action", "actions", "action_list"),
}

# Flat scalar keys (real MissionState fields) used to derive a RevenueMetric
# when no explicit revenue_metrics list is supplied.
_REVENUE_SCALAR_KEYS = ("mrr", "burn_rate", "burn", "runway_days", "runway")


def _coerce_state(state: Any) -> dict:
    """Normalize the input into a plain dict.

    Accepts a ``dict`` directly, a Pydantic model (``model_dump``), or any
    dataclass / object (``asdict`` / ``vars``). Falls back to ``{}`` if the
    input cannot be normalized.
    """
    if state is None:
        return {}
    if isinstance(state, dict):
        return state
    # Pydantic v2 models
    model_dump = getattr(state, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:  # pragma: no cover - defensive
            pass
    # dataclasses / plain objects
    try:
        from dataclasses import asdict

        return asdict(state)  # type: ignore[arg-type]
    except Exception:
        try:
            return dict(vars(state))
        except Exception:
            return {}


def _build_list(model: type[BaseModel], items: Any) -> list[BaseModel]:
    """Validate ``items`` into a list of ``model`` instances.

    Items that are not dicts, or that fail strict validation, are skipped
    (tolerant — never raises).
    """
    out: list[BaseModel] = []
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            out.append(model(**item))
        except (ValidationError, TypeError, ValueError) as exc:
            log.debug("Skipping invalid %s item: %s", model.__name__, exc)
            continue
    return out


def _derive_revenue_metric(data: dict) -> RevenueMetric | None:
    """Build a single RevenueMetric from flat finance scalars, if present.

    A scalar key present but set to ``None`` is treated as *absent* — we do
    not synthesize a zero-valued metric from missing data.
    """
    if not any(data.get(k) is not None for k in _REVENUE_SCALAR_KEYS):
        return None

    raw_mrr = data.get("mrr")
    raw_burn = data.get("burn_rate", data.get("burn"))
    raw_runway = data.get("runway_days", data.get("runway"))

    try:
        return RevenueMetric(
            period=str(data.get("period", "current")),
            mrr=float(raw_mrr) if raw_mrr is not None else 0.0,
            burn=float(raw_burn) if raw_burn is not None else 0.0,
            runway_days=int(raw_runway) if raw_runway is not None else 0,
        )
    except (ValidationError, TypeError, ValueError) as exc:
        log.debug("Could not derive RevenueMetric: %s", exc)
        return None


def mission_state_to_ontology(state: dict) -> dict[str, list[BaseModel]]:
    """Map a flat ``MissionState`` dict into typed Object Type lists.

    Args:
        state: A flat ``MissionState`` mapping (dict, or any object that can
            be normalized to a dict). Missing keys simply produce empty lists;
            unknown / legacy keys are ignored.

    Returns:
        A dict keyed by the six Object Type names
        (``"Customer"``, ``"Deal"``, ``"RevenueMetric"``, ``"Incident"``,
        ``"Message"``, ``"PlannedAction"``) whose values are lists of the
        corresponding validated Pydantic models. An empty input returns ``{}``.
    """
    data = _coerce_state(state)
    if not data:
        return {}

    result: dict[str, list[BaseModel]] = {name: [] for name in OBJECT_TYPES}

    # 1) Explicit list-valued keys for each Object Type.
    for name, keys in _LIST_KEYS.items():
        model = OBJECT_TYPES[name]
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                result[name].extend(_build_list(model, value))
                break

    # 2) Derive a RevenueMetric from flat finance scalars if none supplied.
    if not result["RevenueMetric"]:
        derived = _derive_revenue_metric(data)
        if derived is not None:
            result["RevenueMetric"].append(derived)

    return result
