"""Control Plane idempotency — domain-key builder + in-memory seen-set.

The key is a domain key (``tenant+mission+action_type+target+
business_scope``): stable across retries and safe to use as the
Temporal workflow/activity id and the Redpanda message key.

It is NOT a thread+sequence key: thread identity is untrusted
planner output and sequence numbers do not survive replays.
"""

from __future__ import annotations


def build_idempotency_key(
    tenant_id: str,
    mission_id: str,
    action_type: str,
    target_reference: str,
    business_scope: str = "",
) -> str:
    """Build a deterministic, replay-safe domain idempotency key."""
    parts = [tenant_id, mission_id, action_type, target_reference, business_scope or "-"]
    return ":".join(parts)


class SeenSet:
    """In-memory replay guard (single-process scaffold).

    Production binds the same key to Temporal idempotency ids and
    Redpanda exactly-once keys; the store there is durable, not this set.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def is_duplicate(self, key: str) -> bool:
        """Return True when *key* was already executed in this process."""
        return key in self._seen

    def mark(self, key: str) -> None:
        """Record *key* as executed."""
        self._seen.add(key)
