"""OntologyAI V5.1 — Governed Write Enforcement (PRD §10.7, §18).

Provides the :func:`governed_write` decorator that enforces human-in-the-loop
(HITL) approval for consequential writes to ontology Object Type properties.

Design
------
The decorator mirrors the existing Temporal ``AwaitWithTimeout`` HITL pattern:
a consequential write is *never* silently committed. Instead it must be
associated with a ``PlannedAction`` record and is blocked pending human
approval.

Two independent gates trigger the requirement for a ``PlannedAction``:

1. **Explicit flag** — the property is flagged ``requires_approval=True`` in the
   write policy.
2. **Blast-radius threshold** — the effective blast radius of the write is at or
   above the configured threshold (default ``"medium"``), i.e. ``"medium"`` /
   ``"high"`` require a PlannedAction while ``"low"`` writes proceed.

When a ``PlannedAction`` is required the decorator:

* raises :class:`GovernanceError` if no ``PlannedAction`` can be produced
  (neither passed in nor buildable via a ``create_planned_action`` callback),
  OR
* creates/uses the ``PlannedAction`` and **returns it** to the caller, who must
  submit it for approval before the real write executes. The underlying write
  function is intentionally *not* invoked — this is the block.

Writes that fall below the threshold and are not flagged commit directly.

The policy source (``OBJECT_WRITE_POLICY``) is overridable per-decorator and
per-test, so the governance contract can be exercised in isolation.
"""
from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Optional

from src.ontology.action_types import PlannedAction
from src.ontology.object_types import OBJECT_TYPES

log = logging.getLogger(__name__)

# Blast-radius ordering used for threshold comparisons.
_BLAST_RANK = {"low": 1, "medium": 2, "high": 3}

# Default write policy: object_type -> {property_name -> policy}.
#   requires_approval : always require a PlannedAction for this property.
#   blast_radius      : inherent blast radius of writes to this property; writes
#                       at/above the decorator threshold require a PlannedAction.
#
# Keyed by the six canonical Object Types (PRD §12). Medium/high blast radius
# and any external-side-effect property requires approval (PRD §18.1).
OBJECT_WRITE_POLICY: dict[str, dict[str, dict[str, Any]]] = {
    "Party": {
        # Changing ownership of a party is a medium-blast write.
        "owner": {"requires_approval": True, "blast_radius": "medium"},
        "status": {"requires_approval": False, "blast_radius": "low"},
    },
    "Engagement": {
        "status": {"requires_approval": False, "blast_radius": "low"},
        "value": {"requires_approval": False, "blast_radius": "low"},
        "owner": {"requires_approval": True, "blast_radius": "medium"},
    },
    "MoneyEvent": {
        # Any change to money state is a high-blast write.
        "status": {"requires_approval": True, "blast_radius": "high"},
        "amount": {"requires_approval": True, "blast_radius": "high"},
    },
    "Issue": {
        # Closing an issue without evidence is gated (PRD §18.1).
        "status": {"requires_approval": True, "blast_radius": "medium"},
        "severity": {"requires_approval": False, "blast_radius": "medium"},
        "owner": {"requires_approval": True, "blast_radius": "medium"},
    },
    "Message": {
        # Outbound communication is a high-blast write.
        "direction": {"requires_approval": True, "blast_radius": "high"},
        "summary": {"requires_approval": False, "blast_radius": "low"},
    },
    "PlannedAction": {
        # Executing / completing an action is a governance-gated side effect.
        "status": {"requires_approval": True, "blast_radius": "high"},
    },
}


class GovernanceError(Exception):
    """Raised when a governed write is attempted without required approval."""


def _rank(blast: str) -> int:
    """Return the numeric rank of a blast radius (unknown -> low)."""
    return _BLAST_RANK.get(blast, 1)


def default_create_planned_action(
    object_type: str,
    property_name: str,
    blast_radius: str,
    requested_by: str = "system",
    **kwargs: Any,
) -> PlannedAction:
    """Build a default ontology ``PlannedAction`` for a blocked write."""
    target_id = kwargs.get("target_id", object_type)
    return PlannedAction(
        id=kwargs.get("id") or f"pa-{object_type}-{property_name}",
        type=f"write:{object_type}.{property_name}",
        title=f"Write {object_type}.{property_name} on {target_id}",
        blast_radius=blast_radius,  # type: ignore[arg-type]
        status="draft",
        requested_by=requested_by,
        target_object_type=object_type if object_type in OBJECT_TYPES else "Workflow",  # type: ignore[arg-type]
        target_id=str(target_id),
        rationale=f"Governed write to {object_type}.{property_name}",
        requires_approval=True,
        source_refs=kwargs.get("source_refs", []),
    )


def governed_write(
    object_type: str,
    property_name: str,
    policy: Optional[dict] = None,
    create_planned_action: Optional[Callable[..., PlannedAction]] = None,
    threshold: str = "medium",
    requested_by: str = "system",
):
    """Decorator enforcing governed (HITL-approved) writes to an ontology property.

    Args:
        object_type: Ontology Object Type name (e.g. ``"Party"``).
        property_name: Property being written (e.g. ``"owner"``).
        policy: Optional policy dict overriding ``OBJECT_WRITE_POLICY``.
        create_planned_action: Optional callback used to materialize the
            PlannedAction record when one is required.
        threshold: Minimum blast radius that triggers a PlannedAction requirement
            (default ``"medium"`` — ``"low"`` writes proceed without approval).
        requested_by: Actor requesting the write (recorded on the PlannedAction).

    The wrapped function accepts two optional keyword arguments consumed by the
    decorator:
        * ``blast_radius`` — override the effective blast radius of this write.
        * ``planned_action`` — an already-built ``PlannedAction`` to associate.
    """
    policy_source = policy if policy is not None else OBJECT_WRITE_POLICY

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            entry = (policy_source.get(object_type) or {}).get(property_name, {})
            requires_approval = bool(entry.get("requires_approval", False))
            prop_blast = entry.get("blast_radius", "low")

            # Effective blast radius of this specific write (caller may override).
            blast = kwargs.pop("blast_radius", prop_blast)

            needs_action = requires_approval or (_rank(blast) >= _rank(threshold))

            if not needs_action:
                # Below threshold and not flagged: commit directly.
                return fn(*args, **kwargs)

            # A PlannedAction is required — block the write (HITL pattern).
            create_cb = kwargs.pop("create_planned_action", create_planned_action)
            planned = kwargs.pop("planned_action", None)
            if planned is None and create_cb is not None:
                planned = create_cb(
                    object_type=object_type,
                    property_name=property_name,
                    blast_radius=blast,
                    requested_by=requested_by,
                    **kwargs,
                )

            if planned is None:
                # No PlannedAction could be produced — hard block.
                raise GovernanceError(
                    f"Governed write to {object_type}.{property_name} "
                    f"(blast_radius={blast}, requires_approval={requires_approval}) "
                    f"requires a PlannedAction and human approval before it can commit."
                )

            # Block: return the PlannedAction for the caller to approve.
            log.info(
                "Blocked governed write %s.%s (blast_radius=%s) — PlannedAction %s "
                "pending approval",
                object_type,
                property_name,
                blast,
                getattr(planned, "id", "?"),
            )
            return planned

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Reference implementations — one governed write path per specialist.
# These are thin wrappers demonstrating @governed_write on the new types.
# The underlying write is a minimal, side-effect-free stand-in.
# ---------------------------------------------------------------------------

def _party_owner_change_underlying(party_id: str, owner: str) -> dict:
    return {"updated": party_id, "owner": owner}


@governed_write(object_type="Party", property_name="owner", requested_by="OntologyMapper")
def governed_party_owner_change(party_id: str, owner: str, **kwargs: Any) -> Any:
    """Governed ownership change on a Party (medium blast radius)."""
    return _party_owner_change_underlying(party_id, owner)


def _money_state_change_underlying(event_id: str, status: str) -> dict:
    return {"updated": event_id, "status": status}


@governed_write(object_type="MoneyEvent", property_name="status", requested_by="TruthAnalyst")
def governed_money_state_change(event_id: str, status: str, **kwargs: Any) -> Any:
    """Governed money-state change (high blast radius)."""
    return _money_state_change_underlying(event_id, status)


def _issue_close_underlying(issue_id: str, status: str) -> dict:
    return {"updated": issue_id, "status": status}


@governed_write(object_type="Issue", property_name="status", requested_by="TruthAnalyst")
def governed_issue_close(issue_id: str, status: str, **kwargs: Any) -> Any:
    """Governed issue close (medium blast radius, requires approval)."""
    return _issue_close_underlying(issue_id, status)


def _message_send_underlying(channel: str, text: str) -> dict:
    return {"sent": True, "channel": channel}


@governed_write(object_type="Message", property_name="direction", requested_by="Discovery")
def governed_message_send(channel: str, text: str, **kwargs: Any) -> Any:
    """Governed outbound communication (high blast radius)."""
    return _message_send_underlying(channel, text)
