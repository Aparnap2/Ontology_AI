"""Control Plane idempotency — domain-key builder + at-most-once guard.

The key is a domain key (``tenant+mission+action_type+target+
business_scope``): stable across retries and safe to use as the
Temporal workflow/activity id and the Redpanda message key.

It is NOT a thread+sequence key: thread identity is untrusted
planner output and sequence numbers do not survive replays.

Concurrency
-----------
An earlier version exposed only ``is_duplicate``/``mark``, which the ingress
path used as check-then-act: the key was recorded only *after* execution
completed, so every concurrent submitter inside the execution window passed
the check and executed. Four concurrent submissions of one key produced four
side effects.

``claim`` replaces that with an atomic reservation::

    CLAIM(key) --+-- already claimed --> DUPLICATE
                 +-- claimed          --> EXECUTE
                                              +-- success --> COMMIT
                                              +-- failure --> RELEASE

A claim is held under an owner token and a lease. ``commit``/``release``
only accept the holder's token, so a stale worker cannot free or complete
another owner's claim, and an expired PENDING lease is reclaimable so a
worker that dies mid-execution cannot wedge the key forever. ``COMMITTED``
is terminal and is never released by a lease sweep.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Literal


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


#: Terminal — the action executed; the key must never run again.
COMMITTED = "COMMITTED"
#: Reserved but not finished; retryable after the lease expires or release.
PENDING = "PENDING"
#: Never claimed.
ABSENT = "ABSENT"

State = Literal["ABSENT", "PENDING", "COMMITTED"]

#: Default claim lease. A worker that dies mid-execution releases the key
#: after this long, trading a small duplicate risk for liveness.
DEFAULT_LEASE_SECONDS = 300.0


class IdempotencyConflictError(Exception):
    """The same idempotency key was presented with a different payload.

    Collapsing this into a plain duplicate would silently drop a genuinely
    different request, so it is surfaced explicitly.
    """


class _Entry:
    """One claimed key."""

    __slots__ = ("state", "owner", "payload_hash", "claimed_at", "lease_until")

    def __init__(
        self,
        state: str,
        owner: str,
        payload_hash: str,
        claimed_at: float,
        lease_until: float,
    ) -> None:
        self.state = state
        self.owner = owner
        self.payload_hash = payload_hash
        self.claimed_at = claimed_at
        self.lease_until = lease_until


class SeenSet:
    """In-memory at-most-once guard with an atomic claim.

    Production binds the same key to Temporal idempotency ids and Redpanda
    exactly-once keys, where the store is durable rather than this process.
    The claim/commit/release protocol is the same in both cases; only the
    atomicity primitive differs (``INSERT ... ON CONFLICT DO NOTHING`` in
    Postgres, ``SET NX`` in Redis).
    """

    def __init__(self) -> None:
        # A single lock makes claim a compare-and-set with respect to every
        # other caller in this process, which is what removes the
        # check-then-act window.
        self._lock = threading.Lock()
        self._entries: dict[str, _Entry] = {}

    # -- atomic reservation -------------------------------------------------

    def claim(
        self,
        key: str,
        owner: str,
        payload_hash: str = "",
        *,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
    ) -> bool:
        """Atomically reserve *key* for *owner*.

        Returns True when the caller won the reservation and may execute.
        Returns False when the key is already PENDING under a live lease or
        already COMMITTED.

        Raises:
            IdempotencyConflictError: the key exists with a different
                ``payload_hash``, i.e. a different request is reusing an
                idempotency key.
        """
        now = time.monotonic()
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None:
                if existing.payload_hash and payload_hash:
                    if existing.payload_hash != payload_hash:
                        raise IdempotencyConflictError(
                            f"idempotency key {key!r} reused with a different "
                            "payload"
                        )
                if existing.state == COMMITTED:
                    return False
                # PENDING: reclaimable only once the lease has expired.
                if existing.lease_until > now:
                    return False
            self._entries[key] = _Entry(
                state=PENDING,
                owner=owner,
                payload_hash=payload_hash,
                claimed_at=now,
                lease_until=now + lease_seconds,
            )
            return True

    def commit(self, key: str, owner: str) -> None:
        """Mark *key* executed. Only the claim holder may commit.

        Raises:
            PermissionError: *owner* does not hold the claim.
            KeyError: no claim exists for *key*.
        """
        with self._lock:
            holder = self._require_holder(key, owner)
            holder.state = COMMITTED
            holder.lease_until = float("inf")

    def release(self, key: str, owner: str) -> None:
        """Release *key* so a retry may execute. Only the holder may release.

        Raises:
            PermissionError: *owner* does not hold the claim.
            KeyError: no claim exists for *key*.
        """
        with self._lock:
            self._require_holder(key, owner)
            del self._entries[key]

    # -- introspection ------------------------------------------------------

    def state_of(self, key: str) -> State:
        """Return ABSENT, PENDING or COMMITTED for *key*."""
        with self._lock:
            entry = self._entries.get(key)
            return entry.state if entry else ABSENT  # type: ignore[return-value]

    def owner_of(self, key: str) -> str | None:
        """Return the current claim holder, or None."""
        with self._lock:
            entry = self._entries.get(key)
            return entry.owner if entry else None

    def _expire_leases(self) -> int:
        """Drop PENDING claims whose lease expired. Returns the count.

        COMMITTED entries are terminal and are never released here.
        """
        now = time.monotonic()
        with self._lock:
            stale = [
                k
                for k, e in self._entries.items()
                if e.state == PENDING and e.lease_until <= now
            ]
            for k in stale:
                del self._entries[k]
            return len(stale)

    # -- legacy API (kept: the existing P0/security suite depends on it) -----

    def is_duplicate(self, key: str) -> bool:
        """Return True when *key* was already committed or is in flight."""
        return self.state_of(key) != ABSENT

    def mark(self, key: str) -> None:
        """Record *key* as executed (legacy fire-and-forget)."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._entries[key] = _Entry(
                    state=COMMITTED,
                    owner="",
                    payload_hash="",
                    claimed_at=time.monotonic(),
                    lease_until=float("inf"),
                )
            else:
                entry.state = COMMITTED
                entry.lease_until = float("inf")

    # -- internals ----------------------------------------------------------

    def _require_holder(self, key: str, owner: str) -> _Entry:
        entry = self._entries.get(key)
        if entry is None:
            raise KeyError(f"no claim held for idempotency key {key!r}")
        if entry.owner != owner:
            raise PermissionError(
                f"idempotency key {key!r} is held by {entry.owner!r}, "
                f"not {owner!r}"
            )
        return entry

    def keys(self) -> set[str]:
        """Return the set of currently held keys (inspection/test seam)."""
        with self._lock:
            return set(self._entries)

    def clear(self) -> None:
        """Drop all claims (test seam only)."""
        with self._lock:
            self._entries.clear()

    @property
    def _seen(self) -> set[str]:
        """Snapshot of held keys, for read-only introspection.

        Earlier revisions exposed the backing set here and callers invoked
        ``._seen.clear()``. That is no longer supported: this returns a
        snapshot, so clearing it would be a silent no-op. Use ``clear()``
        (or ``reset_seen()``) to drop claims, and ``keys()`` to read them.
        """
        return self.keys()


def _noop(*_args: Any, **_kwargs: Any) -> None:
    return None


_seen = SeenSet()


def get_seen() -> SeenSet:
    """Return the process-wide seen set."""
    return _seen


def reset_seen() -> None:
    """Clear all recorded keys (test seam only)."""
    _seen.clear()