"""Control Plane optimistic concurrency — version gate for contested targets.

A planner that read state at version N may only mutate when the target is
still at N. The gate lives in :mod:`ingress` and fires ONLY when
``authorized.expected_version is not None`` (default None → zero behavior
change). Mismatch fails closed: audited ``deny:stale_version``, no
execution, no blind overwrite, no idempotency mark — the caller refreshes
and resubmits. Versions advance only after :mod:`executor` returns.
"""

from __future__ import annotations


class VersionStore:
    """In-memory target-version registry (single-process scaffold).

    Production binds the same ``tenant:mission`` key to a durable
    compare-and-swap; the store there is transactional, not this dict.
    """

    def __init__(self) -> None:
        self._versions: dict[str, int] = {}

    def seed(self, key: str, version: int) -> None:
        """Record the version a planner observed (test/replay seam)."""
        self._versions[key] = int(version)

    def current(self, key: str) -> int | None:
        """Return the recorded version, or None when never observed."""
        value = self._versions.get(key)
        return None if value is None else int(value)

    def advance(self, key: str) -> int:
        """Move the recorded version forward by one; return the new value."""
        new_value = int(self._versions.get(key, -1)) + 1
        self._versions[key] = new_value
        return new_value


_store = VersionStore()


def get_store() -> VersionStore:
    """Return the process-wide version store."""
    return _store


def reset_store() -> None:
    """Clear all recorded versions (test seam only)."""
    _store._versions.clear()
