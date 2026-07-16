"""OntologyAI V5.1 — State → Ontology Adapter.

Maps a flat shared-state dict (``MissionState`` legacy bridge OR the new
``EngagementState``) into the six canonical typed Object Type lists defined in
:mod:`src.ontology.object_types`.

Design goals
------------
* **Tolerant** — unknown / legacy / malformed keys are ignored, never raise.
* **Typed** — every value returned is a validated Pydantic model instance
  (``extra="forbid"`` + ``strict=True`` models), so downstream governance can
  trust the shape.
* **Non-destructive** — the input state is never mutated.

Compatibility
-------------
* ``mission_state_to_ontology`` keeps working for the legacy ``MissionState``
  flat dict (read-only bridge, PRD §8.1 decision 1). It now maps the legacy
  finance scalars into ``MoneyEvent`` records (the RevenueMetric→MoneyEvent
  migration, PRD §12.3) instead of the removed ``RevenueMetric`` type.
* ``engagement_state_to_ontology`` maps the new canonical ``EngagementState``
  shape (``ontology_objects`` dict keyed by type name) into typed lists.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from src.ontology.object_types import (
    OBJECT_TYPES,
    Engagement,
    Issue,
    Message,
    MoneyEvent,
    Party,
    PlannedAction,
)

log = logging.getLogger(__name__)

# Recognized source keys per Object Type for the legacy MissionState bridge,
# checked in priority order. The first list-valued key found for a type wins.
_LIST_KEYS: dict[str, tuple[str, ...]] = {
    "Party": ("parties", "party", "party_list", "customers"),
    "Engagement": ("engagements", "engagement", "engagement_list", "deals"),
    "MoneyEvent": ("money_events", "money_event", "money", "revenue_metrics"),
    "Issue": ("issues", "issue", "issue_list", "incidents"),
    "Message": ("messages", "message", "message_list"),
    "PlannedAction": ("planned_actions", "planned_action", "actions", "action_list"),
}

# Flat scalar keys (legacy MissionState fields) used to derive MoneyEvents when
# no explicit money_events list is supplied.
_REVENUE_SCALAR_KEYS = ("mrr", "burn_rate", "burn", "runway_days", "runway")


def _coerce_state(state: Any) -> dict:
    """Normalize the input into a plain dict (dict / pydantic / dataclass)."""
    if state is None:
        return {}
    if isinstance(state, dict):
        return state
    model_dump = getattr(state, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:  # pragma: no cover - defensive
            pass
    try:
        from dataclasses import asdict

        return asdict(state)  # type: ignore[arg-type]
    except Exception:
        try:
            return dict(vars(state))
        except Exception:
            return {}


def _build_list(model: type[BaseModel], items: Any) -> list[BaseModel]:
    """Validate ``items`` into a list of ``model`` instances (tolerant)."""
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


def _derive_money_events(data: dict) -> list[MoneyEvent]:
    """Build MoneyEvent(s) from flat finance scalars, if present.

    A scalar key present but set to ``None`` is treated as *absent*.
    """
    if not any(data.get(k) is not None for k in _REVENUE_SCALAR_KEYS):
        return []

    events: list[MoneyEvent] = []
    raw_mrr = data.get("mrr")
    raw_burn = data.get("burn_rate", data.get("burn"))
    raw_runway = data.get("runway_days", data.get("runway"))

    if raw_mrr is not None:
        try:
            events.append(
                MoneyEvent(
                    id="me-revenue-mrr",
                    kind="receivable",
                    amount=float(raw_mrr),
                    currency=str(data.get("currency", "USD")),
                    status="open",
                    source_refs=["derived:mission_state.mrr"],
                )
            )
        except (ValidationError, TypeError, ValueError) as exc:
            log.debug("Could not derive MRR MoneyEvent: %s", exc)

    if raw_burn is not None:
        try:
            events.append(
                MoneyEvent(
                    id="me-burn",
                    kind="expense",
                    amount=float(raw_burn),
                    currency=str(data.get("currency", "USD")),
                    status="open",
                    source_refs=["derived:mission_state.burn"],
                )
            )
        except (ValidationError, TypeError, ValueError) as exc:
            log.debug("Could not derive burn MoneyEvent: %s", exc)

    return events


def mission_state_to_ontology(state: Any) -> dict[str, list[BaseModel]]:
    """Map a legacy flat ``MissionState`` dict into typed Object Type lists.

    Kept as a read-only bridge (PRD §8.1 decision 1). Returns a dict keyed by
    the six Object Type names whose values are lists of validated models.
    """
    data = _coerce_state(state)
    if not data:
        return {}

    result: dict[str, list[BaseModel]] = {name: [] for name in OBJECT_TYPES}

    for name, keys in _LIST_KEYS.items():
        model = OBJECT_TYPES[name]
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                result[name].extend(_build_list(model, value))
                break

    # Derive MoneyEvents from flat finance scalars if none supplied.
    if not result["MoneyEvent"]:
        result["MoneyEvent"].extend(_derive_money_events(data))

    return result


def engagement_state_to_ontology(state: Any) -> dict[str, list[BaseModel]]:
    """Map a canonical ``EngagementState`` dict into typed Object Type lists.

    The ``EngagementState.ontology_objects`` field is a dict keyed by Object
    Type name (``"Party"``, ``"Engagement"``, ...) whose values are lists of
    dicts. Each dict is validated into the corresponding model.
    """
    data = _coerce_state(state)
    if not data:
        return {}

    raw_objects = data.get("ontology_objects", {})
    if not isinstance(raw_objects, dict):
        raw_objects = {}

    result: dict[str, list[BaseModel]] = {name: [] for name in OBJECT_TYPES}
    for name, model in OBJECT_TYPES.items():
        items = raw_objects.get(name)
        if isinstance(items, list):
            result[name].extend(_build_list(model, items))
    return result
