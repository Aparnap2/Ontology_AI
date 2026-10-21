"""OntologyAI V5.2 — Link Type registry and resolver (PRD §13).

Defines the 11 canonical semantic links between Object Types and a
``resolve_link`` helper that queries an injectable data backend for the
linked object IDs.

Expected ``db`` interface
-------------------------
``resolve_link`` accepts either:

* a **callable** with signature
  ``db(source_type: str, source_id: str, link_name: str) -> list[str]``,
  or
* an **object** exposing a method
  ``db.fetch_links(source_type: str, source_id: str, link_name: str) -> list[str]``.

This keeps the helper fully testable without a real Postgres connection.
"""
from pydantic import BaseModel, ConfigDict

from src.ontology.object_types import OBJECT_TYPES


class LinkType(BaseModel):
    """A canonical semantic link between two Object Types (PRD §13)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    source_type: str
    target_type: str
    cardinality: str
    semantic_meaning: str
    source_refs: list[str] = []


# The 11 canonical link types (PRD §13). Each entry is a LinkType instance.
LINK_TYPES: dict[str, LinkType] = {
    "party_engagement": LinkType(
        name="party_engagement",
        source_type="Party",
        target_type="Engagement",
        cardinality="one_to_many",
        semantic_meaning="A party is associated with one or more engagements.",
        source_refs=["prd §13"],
    ),
    "engagement_money_event": LinkType(
        name="engagement_money_event",
        source_type="Engagement",
        target_type="MoneyEvent",
        cardinality="one_to_many",
        semantic_meaning="An engagement produces or is tied to money events.",
        source_refs=["prd §13"],
    ),
    "engagement_issue": LinkType(
        name="engagement_issue",
        source_type="Engagement",
        target_type="Issue",
        cardinality="one_to_many",
        semantic_meaning="An engagement may surface issues/blockers.",
        source_refs=["prd §13"],
    ),
    "message_party": LinkType(
        name="message_party",
        source_type="Message",
        target_type="Party",
        cardinality="many_to_many",
        semantic_meaning="A message involves one or more parties.",
        source_refs=["prd §13"],
    ),
    "message_engagement": LinkType(
        name="message_engagement",
        source_type="Message",
        target_type="Engagement",
        cardinality="many_to_many",
        semantic_meaning="A message references one or more engagements.",
        source_refs=["prd §13"],
    ),
    "issue_planned_action": LinkType(
        name="issue_planned_action",
        source_type="Issue",
        target_type="PlannedAction",
        cardinality="one_to_many",
        semantic_meaning="An issue may be addressed by planned actions.",
        source_refs=["prd §13"],
    ),
    "money_event_planned_action": LinkType(
        name="money_event_planned_action",
        source_type="MoneyEvent",
        target_type="PlannedAction",
        cardinality="one_to_many",
        semantic_meaning="A money event may be resolved by planned actions.",
        source_refs=["prd §13"],
    ),
    "party_planned_action": LinkType(
        name="party_planned_action",
        source_type="Party",
        target_type="PlannedAction",
        cardinality="one_to_many",
        semantic_meaning="A party may be the target of planned actions.",
        source_refs=["prd §13"],
    ),
    "engagement_planned_action": LinkType(
        name="engagement_planned_action",
        source_type="Engagement",
        target_type="PlannedAction",
        cardinality="one_to_many",
        semantic_meaning="An engagement may be the target of planned actions.",
        source_refs=["prd §13"],
    ),
    "workflow_action": LinkType(
        name="workflow_action",
        source_type="Workflow",
        target_type="PlannedAction",
        cardinality="one_to_many",
        semantic_meaning="A workflow produces or triggers planned actions.",
        source_refs=["prd §13"],
    ),
    "workflow_object_dependency": LinkType(
        name="workflow_object_dependency",
        source_type="Workflow",
        target_type="*",
        cardinality="many_to_many",
        semantic_meaning="A workflow depends on one or more ontology objects.",
        source_refs=["prd §13"],
    ),
    "order_shipment": LinkType(
        name="order_shipment",
        source_type="Engagement",
        target_type="Shipment",
        cardinality="one_to_many",
        semantic_meaning="An order (Engagement kind='order') is fulfilled by one or more shipments.",
        source_refs=["revenue_protection_slice"],
    ),
    # ── V6 domain links (Virtual COO operating model) ──────────────────────
    "stakeholder_owns_process": LinkType(
        name="stakeholder_owns_process",
        source_type="Stakeholder",
        target_type="Process",
        cardinality="one_to_many",
        semantic_meaning="A stakeholder owns or sponsors one or more processes.",
        source_refs=["v6_frozen_direction"],
    ),
    "process_has_sop": LinkType(
        name="process_has_sop",
        source_type="Process",
        target_type="SOP",
        cardinality="one_to_many",
        semantic_meaning="A process is documented by one or more SOPs.",
        source_refs=["v6_frozen_direction"],
    ),
    "sop_versions": LinkType(
        name="sop_versions",
        source_type="SOP",
        target_type="SOPVersion",
        cardinality="one_to_many",
        semantic_meaning="An SOP has a version history.",
        source_refs=["v6_frozen_direction"],
    ),
    "employee_runs_mission": LinkType(
        name="employee_runs_mission",
        source_type="Employee",
        target_type="Mission",
        cardinality="one_to_many",
        semantic_meaning="An AI employee runs one or more missions.",
        source_refs=["v6_frozen_direction"],
    ),
    "mission_involves_process": LinkType(
        name="mission_involves_process",
        source_type="Mission",
        target_type="Process",
        cardinality="many_to_many",
        semantic_meaning="A mission operates on one or more processes.",
        source_refs=["v6_frozen_direction"],
    ),
    "mission_generates_actions": LinkType(
        name="mission_generates_actions",
        source_type="Mission",
        target_type="Action",
        cardinality="one_to_many",
        semantic_meaning="A mission generates governed actions.",
        source_refs=["v6_frozen_direction"],
    ),
    "action_targets_entity": LinkType(
        name="action_targets_entity",
        source_type="Action",
        target_type="*",
        cardinality="many_to_one",
        semantic_meaning="An action targets any ontology entity.",
        source_refs=["v6_frozen_direction"],
    ),
    "action_result_from": LinkType(
        name="action_result_from",
        source_type="ActionResult",
        target_type="Action",
        cardinality="many_to_one",
        semantic_meaning="An action result belongs to an action.",
        source_refs=["v6_frozen_direction"],
    ),
    "action_results_of": LinkType(
        name="action_results_of",
        source_type="Action",
        target_type="ActionResult",
        cardinality="one_to_many",
        semantic_meaning="An action produces one or more results.",
        source_refs=["v6_frozen_direction"],
    ),
    "review_of_process": LinkType(
        name="review_of_process",
        source_type="Review",
        target_type="Process",
        cardinality="many_to_one",
        semantic_meaning="A review is conducted against a process.",
        source_refs=["v6_frozen_direction"],
    ),
    "outcome_of_mission": LinkType(
        name="outcome_of_mission",
        source_type="Outcome",
        target_type="Mission",
        cardinality="many_to_one",
        semantic_meaning="An outcome is the result of a mission.",
        source_refs=["v6_frozen_direction"],
    ),
    "kpi_monitors_entity": LinkType(
        name="kpi_monitors_entity",
        source_type="KPI",
        target_type="*",
        cardinality="many_to_one",
        semantic_meaning="A KPI monitors any ontology entity.",
        source_refs=["v6_frozen_direction"],
    ),
}


def resolve_link(link_name: str, source_id: str, db=None) -> list[str]:
    """Resolve the target object IDs linked to ``source_id`` via ``link_name``.

    Args:
        link_name: The semantic link name (must exist in ``LINK_TYPES``).
        source_id: The ID of the source object.
        db: Optional injectable backend. May be: a callable ``db(source_type,
            source_id, link_name) -> list[str]``; an object exposing a
            ``fetch_links(source_type, source_id, link_name)`` method; or a
            mapping keyed by ``(source_type, source_id, link_name)`` to a list
            of target IDs. If omitted, an empty list is returned.

    Returns:
        A list of linked target object IDs (possibly empty).

    Raises:
        KeyError: If ``link_name`` is not present in ``LINK_TYPES``.
    """
    if link_name not in LINK_TYPES:
        raise KeyError(f"Unknown link type: {link_name!r}")

    if db is None:
        return []

    source_type = LINK_TYPES[link_name].source_type

    if callable(db):
        return db(source_type, source_id, link_name)

    if isinstance(db, dict):
        return list(db.get((source_type, source_id, link_name), []) or [])

    fetch = getattr(db, "fetch_links", None)
    if callable(fetch):
        return fetch(source_type, source_id, link_name)

    raise TypeError(
        "db must be a callable or an object exposing 'fetch_links'; "
        f"got {type(db).__name__!r}"
    )


def validate_link_types() -> None:
    """Assert every link references a known object type (or the wildcard)."""
    for name, lt in LINK_TYPES.items():
        assert lt.source_type in OBJECT_TYPES or lt.source_type == "Workflow" or lt.source_type == "*", (
            f"Link {name} has unknown source_type {lt.source_type}"
        )
        assert lt.target_type in OBJECT_TYPES or lt.target_type == "Workflow" or lt.target_type == "*", (
            f"Link {name} has unknown target_type {lt.target_type}"
        )
