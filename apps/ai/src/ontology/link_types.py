"""OntologyAI V4.2 — Link Type registry and resolver.

Defines the canonical semantic links between Object Types and a
``resolve_link`` helper that queries an injectable data backend for the
linked object IDs.

Expected ``db`` interface
--------------------------
``resolve_link`` accepts either:

* a **callable** with signature
  ``db(source_type: str, source_id: str, link_name: str) -> list[str]``,
  or
* an **object** exposing a method
  ``db.fetch_links(source_type: str, source_id: str, link_name: str) -> list[str]``.

This keeps the helper fully testable without a real Postgres connection.
In production a thin wrapper around ``asyncpg``/``psycopg2`` can be passed
that implements ``fetch_links`` (or the callable form) by querying the
``ontology_links`` table, e.g.::

    SELECT target_id FROM ontology_links
    WHERE source_type = $1 AND source_id = $2 AND link_name = $3;
"""
from typing import Callable, Optional, Union

# A db backend is either a callable or an object with a ``fetch_links`` method.
DBLike = Union[
    Callable[[str, str, str], list[str]],
    object,
]


LINK_TYPES: dict[str, tuple[str, str, str]] = {
    "incident_affects_customer": ("Incident", "Customer", "many_to_many"),
    "deal_belongs_to_customer": ("Deal", "Customer", "many_to_one"),
    "message_relates_to_deal": ("Message", "Deal", "many_to_one"),
    "action_targets_object": ("PlannedAction", "*", "polymorphic"),
}


def resolve_link(link_name: str, source_id: str, db=None) -> list[str]:
    """Resolve the target object IDs linked to ``source_id`` via ``link_name``.

    Args:
        link_name: The semantic link name (must exist in ``LINK_TYPES``).
        source_id: The ID of the source object.
        db: Optional injectable backend (callable or object with
            ``fetch_links``). If omitted, an empty list is returned.

    Returns:
        A list of linked target object IDs (possibly empty).

    Raises:
        KeyError: If ``link_name`` is not present in ``LINK_TYPES``.
    """
    if link_name not in LINK_TYPES:
        raise KeyError(f"Unknown link type: {link_name!r}")

    if db is None:
        return []

    source_type = LINK_TYPES[link_name][0]

    if callable(db):
        return db(source_type, source_id, link_name)

    fetch = getattr(db, "fetch_links", None)
    if callable(fetch):
        return fetch(source_type, source_id, link_name)

    raise TypeError(
        "db must be a callable or an object exposing 'fetch_links'; "
        f"got {type(db).__name__!r}"
    )
