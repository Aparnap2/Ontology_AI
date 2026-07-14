"""OntologyAI V4.2 — Governed Write Enforcement (Task 3).

Provides the :func:`governed_write` decorator that enforces human-in-the-loop
(HITL) approval for consequential writes to ontology Object Type properties.

Design
------
The decorator mirrors the existing Temporal ``AwaitWithTimeout`` HITL pattern
used elsewhere in the system: a consequential write is *never* silently
committed. Instead it must be associated with a ``PlannedAction`` record and is
blocked pending human approval.

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

from src.ontology.object_types import PlannedAction

log = logging.getLogger(__name__)

# Blast-radius ordering used for threshold comparisons.
_BLAST_RANK = {"low": 1, "medium": 2, "high": 3}

# Default write policy: object_type -> {property_name -> policy}.
#   requires_approval : always require a PlannedAction for this property.
#   blast_radius      : inherent blast radius of writes to this property; writes
#                       at/above the decorator threshold require a PlannedAction.
#
# This is the canonical, easily-overridable policy source. Specialist reference
# wrappers below rely on these entries to demonstrate governed writes.
OBJECT_WRITE_POLICY: dict[str, dict[str, dict[str, Any]]] = {
    # FP&A cancellation / collection action (affects revenue).
    "Customer": {
        "mrr": {"requires_approval": True, "blast_radius": "high"},
        # Growth Analytics flag (account health flag).
        "health_score": {"requires_approval": True, "blast_radius": "medium"},
    },
    "Deal": {
        "stage": {"requires_approval": False, "blast_radius": "low"},
        "value": {"requires_approval": False, "blast_radius": "low"},
    },
    "RevenueMetric": {
        "burn": {"requires_approval": True, "blast_radius": "high"},
        "runway_days": {"requires_approval": True, "blast_radius": "high"},
    },
    # Reliability incident update (severity change is a medium-blast write).
    "Incident": {
        "severity": {"requires_approval": False, "blast_radius": "medium"},
        "root_cause": {"requires_approval": False, "blast_radius": "low"},
    },
    # Communications outbound send.
    "Message": {
        "drafted_by": {"requires_approval": True, "blast_radius": "high"},
    },
}


class GovernanceError(Exception):
    """Raised when a governed write is attempted without required approval.

    This is the hard-block path: the write could not be associated with a
    ``PlannedAction`` and therefore must not commit.
    """


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
    """Build a default ontology ``PlannedAction`` for a blocked write.

    Used when the decorator must materialize the record itself (no caller-
    supplied ``create_planned_action`` callback). In production this would
    persist the record via the approval queue / state store.
    """
    return PlannedAction(
        id=kwargs.get("id") or f"pa-{object_type}-{property_name}",
        type=f"write:{object_type}.{property_name}",
        blast_radius=blast_radius,  # type: ignore[arg-type]
        status="planned",
        requested_by=requested_by,
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
        object_type: Ontology Object Type name (e.g. ``"Customer"``).
        property_name: Property being written (e.g. ``"mrr"``).
        policy: Optional policy dict overriding ``OBJECT_WRITE_POLICY``. Read at
            call time, so ``monkeypatch`` / per-test overrides work.
        create_planned_action: Optional callback
            ``(object_type, property_name, blast_radius, requested_by, **kw) ->
            PlannedAction`` used to materialize the PlannedAction record when one
            is required. If omitted and no ``planned_action`` is passed, a
            required write raises :class:`GovernanceError`.
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
            # A create callback may be supplied at decoration time or per-call.
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
            # The underlying write is intentionally NOT executed.
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
#
# These are thin wrappers demonstrating how @governed_write is applied to each
# specialist's consequential write. They intentionally do NOT mutate the raw
# activity internals; the underlying write is a minimal, side-effect-free
# stand-in so the governance contract is exercised without external side effects.
# In production each wrapper would invoke the real activity (e.g. the Stripe
# cancellation, the HubSpot flag, the incident update, or the Slack send).
# ---------------------------------------------------------------------------

def _fpa_cancel_underlying(customer_id: str, reason: str) -> dict:
    # Stand-in for the real FP&A cancellation / collection action.
    return {"cancelled": customer_id, "reason": reason}


@governed_write(object_type="Customer", property_name="mrr", requested_by="FP&A")
def governed_fpa_cancel(customer_id: str, reason: str, **kwargs: Any) -> Any:
    """Governed FP&A cancellation / collection action (high blast radius)."""
    return _fpa_cancel_underlying(customer_id, reason)


def _growth_flag_underlying(customer_id: str, flag: str) -> dict:
    # Stand-in for the real Growth Analytics account flag.
    return {"flagged": customer_id, "flag": flag}


@governed_write(object_type="Customer", property_name="health_score", requested_by="Growth Analytics")
def governed_growth_flag(customer_id: str, flag: str, **kwargs: Any) -> Any:
    """Governed Growth Analytics flag (medium blast radius)."""
    return _growth_flag_underlying(customer_id, flag)


def _reliability_incident_update_underlying(incident_id: str, severity: str) -> dict:
    # Stand-in for the real Reliability incident update.
    return {"updated": incident_id, "severity": severity}


@governed_write(object_type="Incident", property_name="severity", requested_by="Reliability & Delivery")
def governed_reliability_incident_update(incident_id: str, severity: str, **kwargs: Any) -> Any:
    """Governed Reliability incident update (medium blast radius)."""
    return _reliability_incident_update_underlying(incident_id, severity)


def _comms_send_underlying(channel: str, text: str) -> dict:
    # Stand-in for the real Communications outbound send.
    return {"sent": True, "channel": channel}


@governed_write(object_type="Message", property_name="drafted_by", requested_by="Communications")
def governed_comms_send(channel: str, text: str, **kwargs: Any) -> Any:
    """Governed Communications outbound send (high blast radius)."""
    return _comms_send_underlying(channel, text)
