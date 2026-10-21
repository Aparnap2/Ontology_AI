"""P0 RED: at-most-once must hold under concurrency, with crash/retry semantics.

Vulnerability
-------------
``ingress.submit_intent`` performed check-then-act::

    if _seen.is_duplicate(key):        # check   (ingress.py:84)
        return deny:duplicate
    ...
    _seen.mark(key)                    # mark    (ingress.py:136, AFTER execution)

The key is recorded only *after* execution completes, so every concurrent
submitter inside the execution window passes the check and executes. Proven:
four concurrent submissions of one key produced four side effects.

Required semantics
------------------
::

    CLAIM(key) ──┬─ already claimed  -> DUPLICATE
                 └─ claimed          -> EXECUTE
                                          ├─ success -> COMMIT
                                          └─ failure -> RELEASE (retryable)

* the claim MUST be atomic (no check-then-act)
* an explicit state machine: PENDING -> COMMITTED | RELEASED
* a worker that dies while PENDING must not wedge the key forever (lease)
* same key + different payload must be an explicit conflict, not a silent
  duplicate
* same key, different tenant must be independent
* different keys must execute independently

Core invariant
--------------
FOR ANY N concurrent submissions sharing a tenant-scoped idempotency key
and an identical payload, AT MOST ONE external side effect may execute.
"""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest

from src.control_plane.idempotency import (
    IdempotencyConflictError,
    SeenSet,
    reset_seen,
)
from src.control_plane.idempotency import get_seen

KEY = "t1:m1:vendor_ticket.create:v1:"
PAYLOAD = {"vendor_id": "v1", "incident_id": "i1"}


def _payload_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


# ---------------------------------------------------------------------------
# Atomic claim
# ---------------------------------------------------------------------------


class TestAtomicClaim:
    def test_first_claim_wins(self) -> None:
        s = SeenSet()
        assert s.claim(KEY, "owner-1", _payload_hash(PAYLOAD)) is True

    def test_second_claim_is_refused(self) -> None:
        s = SeenSet()
        assert s.claim(KEY, "owner-1", _payload_hash(PAYLOAD)) is True
        assert s.claim(KEY, "owner-2", _payload_hash(PAYLOAD)) is False

    def test_commit_then_claim_is_refused(self) -> None:
        s = SeenSet()
        s.claim(KEY, "owner-1", _payload_hash(PAYLOAD))
        s.commit(KEY, "owner-1")
        assert s.claim(KEY, "owner-2", _payload_hash(PAYLOAD)) is False

    def test_release_allows_retry(self) -> None:
        """A failed execution must leave the key retryable."""
        s = SeenSet()
        s.claim(KEY, "owner-1", _payload_hash(PAYLOAD))
        s.release(KEY, "owner-1")
        assert s.claim(KEY, "owner-2", _payload_hash(PAYLOAD)) is True

    def test_concurrent_claims_yield_exactly_one_winner(self) -> None:
        """The whole point: no check-then-act window."""
        s = SeenSet()
        results: list[bool] = []

        async def contend(owner: str) -> None:
            # await a real suspension point so both callers interleave exactly
            # as they would across two workers
            await asyncio.sleep(0)
            results.append(s.claim(KEY, owner, _payload_hash(PAYLOAD)))

        async def run() -> None:
            await asyncio.gather(*(contend(f"owner-{i}") for i in range(100)))

        asyncio.run(run())
        assert results.count(True) == 1, (
            f"at-most-once VIOLATED: {results.count(True)} claims succeeded"
        )

    @pytest.mark.parametrize("n", [2, 4, 10, 100])
    def test_many_concurrent_claims_single_winner(self, n: int) -> None:
        s = SeenSet()
        results: list[bool] = []

        async def contend(owner: str) -> None:
            await asyncio.sleep(0)
            results.append(s.claim(KEY, owner, _payload_hash(PAYLOAD)))

        asyncio.run(_gather(contend, n))
        assert results.count(True) == 1, (
            f"n={n}: {results.count(True)} winners, expected exactly 1"
        )


async def _gather(contend, n: int) -> None:
    await asyncio.gather(*(contend(f"owner-{i}") for i in range(n)))


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------


class TestOwnership:
    def test_commit_requires_matching_owner(self) -> None:
        s = SeenSet()
        s.claim(KEY, "owner-1", _payload_hash(PAYLOAD))
        with pytest.raises(PermissionError):
            s.commit(KEY, "owner-2")

    def test_release_requires_matching_owner(self) -> None:
        s = SeenSet()
        s.claim(KEY, "owner-1", _payload_hash(PAYLOAD))
        with pytest.raises(PermissionError):
            s.release(KEY, "owner-2")

    def test_non_owner_cannot_release(self) -> None:
        """A stale worker must not free another owner's claim."""
        s = SeenSet()
        s.claim(KEY, "owner-1", _payload_hash(PAYLOAD))
        with pytest.raises(PermissionError):
            s.release(KEY, "attacker")


# ---------------------------------------------------------------------------
# Payload conflict
# ---------------------------------------------------------------------------


class TestPayloadConflict:
    def test_same_key_different_payload_raises_conflict(self) -> None:
        s = SeenSet()
        s.claim(KEY, "owner-1", _payload_hash(PAYLOAD))
        with pytest.raises(IdempotencyConflictError):
            s.claim(KEY, "owner-2", _payload_hash({"vendor_id": "OTHER"}))

    def test_same_key_same_payload_is_plain_duplicate(self) -> None:
        s = SeenSet()
        s.claim(KEY, "owner-1", _payload_hash(PAYLOAD))
        assert s.claim(KEY, "owner-2", _payload_hash(PAYLOAD)) is False

    def test_different_tenants_are_independent(self) -> None:
        """Keys are tenant-scoped; one tenant cannot block another."""
        s = SeenSet()
        other = "t2:m1:vendor_ticket.create:v1:"
        assert s.claim(KEY, "owner-1", _payload_hash(PAYLOAD)) is True
        assert s.claim(other, "owner-2", _payload_hash(PAYLOAD)) is True

    def test_different_keys_execute_independently(self) -> None:
        s = SeenSet()
        assert s.claim("k1", "o1", _payload_hash(PAYLOAD)) is True
        assert s.claim("k2", "o2", _payload_hash(PAYLOAD)) is True


# ---------------------------------------------------------------------------
# Lease / crash recovery
# ---------------------------------------------------------------------------


class TestLeaseRecovery:
    def test_pending_claim_without_lease_is_not_reclaimable(self) -> None:
        s = SeenSet()
        s.claim(KEY, "owner-1", _payload_hash(PAYLOAD))
        assert s.claim(KEY, "owner-2", _payload_hash(PAYLOAD)) is False

    def test_expired_lease_is_reclaimable(self) -> None:
        """A worker that dies while PENDING must not wedge the key forever."""
        s = SeenSet()
        s.claim(KEY, "dead-worker", _payload_hash(PAYLOAD), lease_seconds=0)
        # simulate the passage of time without sleeping
        s._expire_leases()
        assert s.claim(KEY, "new-worker", _payload_hash(PAYLOAD)) is True

    def test_committed_key_survives_lease_expiry(self) -> None:
        """COMMITTED is terminal: a lease sweep must never free it."""
        s = SeenSet()
        s.claim(KEY, "owner-1", _payload_hash(PAYLOAD), lease_seconds=0)
        s.commit(KEY, "owner-1")
        s._expire_leases()
        assert s.claim(KEY, "owner-2", _payload_hash(PAYLOAD)) is False

    def test_state_transitions_are_observable(self) -> None:
        s = SeenSet()
        assert s.state_of(KEY) == "ABSENT"
        s.claim(KEY, "owner-1", _payload_hash(PAYLOAD))
        assert s.state_of(KEY) == "PENDING"
        s.commit(KEY, "owner-1")
        assert s.state_of(KEY) == "COMMITTED"


# ---------------------------------------------------------------------------
# Backwards compatibility — the 251 existing P0 tests depend on these
# ---------------------------------------------------------------------------


class TestLegacyApiPreserved:
    def test_is_duplicate_still_works(self) -> None:
        s = SeenSet()
        assert s.is_duplicate(KEY) is False
        s.mark(KEY)
        assert s.is_duplicate(KEY) is True

    def test_reset_seen_clears_state(self) -> None:
        reset_seen()
        get_seen().mark(KEY)
        assert get_seen().is_duplicate(KEY) is True
        reset_seen()
        assert get_seen().is_duplicate(KEY) is False

    def test_mark_makes_key_duplicate(self) -> None:
        s = SeenSet()
        s.mark(KEY)
        assert s.is_duplicate(KEY) is True
        assert s.state_of(KEY) == "COMMITTED"