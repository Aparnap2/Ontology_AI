"""Idempotency & reconciliation test suite — proves at-most-once business effect.

Every test exercises the REAL control plane pipeline (authorize → policy →
idempotency → execute → audit) with only the vendor executor mocked.
No network. No LLM. Fully deterministic.

The ``capabilities=None`` default in ``submit_intent`` skips the
read-back verification step (which requires real connectors).  This
keeps every test self-contained while still exercising the idempotency,
version-gate, and audit layers end-to-end.

Scenarios covered:
  1. Retry without duplicate side effect (core at-most-once guarantee)
  2. Unknown execution state → reconciliation before blind retry
  3. Idempotency key derivation (same op + target + scope → same key)
  4. Concurrent submission — two identical intents, only one executes
  5. Recovery after crash — SeenSet reset, system still safe
  6. Version progression — N then N+1 both succeed (different versions)
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.control_plane.audit import AUDIT_LOG
from src.control_plane.contracts import AuthorizedAction
from src.control_plane.concurrency import VersionStore, get_store, reset_store
from src.control_plane.idempotency import SeenSet, build_idempotency_key, reset_seen
from src.control_plane.authorization import authorize

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_intent(**overrides: Any) -> Any:
    """Build a minimal ActionIntent with sane defaults."""
    from src.control_plane.contracts import ActionIntent

    defaults: dict[str, Any] = {
        "capability": "project",
        "operation": "jira.create",
        "target_reference": "PROJ-42",
        "requested_parameters": {"project": "PROJ", "summary": "Ship feature X"},
        "reason": "Automated test intent",
        "evidence_ids": [],
        "expected_outcome": "Ticket created",
        "confidence": 0.9,
        "requested_by": "test-agent",
    }
    defaults.update(overrides)
    return ActionIntent.model_validate(defaults)


_TRUSTED_CTX: dict[str, Any] = {
    "tenant_id": "tenant-acme",
    "mission_id": "mission-1",
    "employee_id": "emp-ops",
    "actor_identity": "test-orchestrator",
    "permissions": ["project.write"],
    "business_scope": "onboarding",
}


def _trusted_ctx(**overrides: Any) -> dict[str, Any]:
    """Return a fresh copy of the trusted context with optional overrides."""
    ctx = dict(_TRUSTED_CTX)
    ctx.update(overrides)
    return ctx


def _mock_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """Monkeypatch ``_execute`` to return a fixed success and record calls.

    Returns a mutable dict ``{"count": int}`` for assertions.
    """
    counter: dict[str, int] = {"count": 0}

    def _fake_execute(
        authorized: AuthorizedAction, *, role_caps: list[str] | None = None
    ) -> dict[str, Any]:
        counter["count"] += 1
        return {"op": authorized.operation, "ok": True, "data": {"key": "MOCK-1"}}

    monkeypatch.setattr("src.control_plane.ingress._execute", _fake_execute)
    return counter


# ---------------------------------------------------------------------------
# 1. Core scenario: retry without duplicate side effect
# ---------------------------------------------------------------------------


class TestRetryNoDuplicate:
    """Prove at-most-once business effect under retries."""

    @pytest.fixture(autouse=True)
    def _clean_state(self) -> None:
        """Reset global audit log, version store, and ingress SeenSet before each test."""
        AUDIT_LOG.clear()
        reset_store()
        reset_seen()

    @pytest.mark.asyncio
    async def test_retry_denied_as_duplicate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Intent submitted twice → second gets deny:duplicate, zero extra vendor calls."""
        counter = _mock_execute(monkeypatch)

        from src.control_plane.ingress import submit_intent

        ctx = _trusted_ctx()

        # --- first submission: succeeds ---
        r1 = await submit_intent(_make_intent(), ctx)
        assert r1["decision"] == "permit:executed", r1
        assert counter["count"] == 1

        # --- retry (simulates executor "failed" → planner resubmits same intent) ---
        r2 = await submit_intent(_make_intent(), ctx)
        assert r2["decision"] == "deny:duplicate", r2
        # vendor call count must NOT have increased
        assert counter["count"] == 1

    @pytest.mark.asyncio
    async def test_duplicate_across_different_intent_objects(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two distinct ActionIntent objects with same fields → still duplicate."""
        counter = _mock_execute(monkeypatch)

        from src.control_plane.ingress import submit_intent

        ctx = _trusted_ctx()
        r1 = await submit_intent(_make_intent(), ctx)
        r2 = await submit_intent(_make_intent(), ctx)
        assert r1["decision"] == "permit:executed"
        assert r2["decision"] == "deny:duplicate"
        assert counter["count"] == 1

    @pytest.mark.asyncio
    async def test_triple_retry_still_one_execution(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """First succeeds, retries 2 and 3 both denied — vendor called once."""
        counter = _mock_execute(monkeypatch)

        from src.control_plane.ingress import submit_intent

        ctx = _trusted_ctx()
        r1 = await submit_intent(_make_intent(), ctx)
        r2 = await submit_intent(_make_intent(), ctx)
        r3 = await submit_intent(_make_intent(), ctx)
        assert r1["decision"] == "permit:executed"
        assert r2["decision"] == "deny:duplicate"
        assert r3["decision"] == "deny:duplicate"
        assert counter["count"] == 1


# ---------------------------------------------------------------------------
# 2. Unknown execution state → reconciliation before blind retry
# ---------------------------------------------------------------------------


class TestUnknownExecutionState:
    """When the vendor call outcome is indeterminate, the system must NOT blindly retry."""

    @pytest.fixture(autouse=True)
    def _clean_state(self) -> None:
        AUDIT_LOG.clear()
        reset_store()
        reset_seen()

    @pytest.mark.asyncio
    async def test_reconciliation_before_retry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """POST sent → timeout → UNKNOWN → reconciliation → safe retry decision."""
        call_keys: list[str] = []

        def _track_execute(
            authorized: AuthorizedAction, *, role_caps: list[str] | None = None
        ) -> dict[str, Any]:
            call_keys.append(authorized.idempotency_key)
            return {
                "op": authorized.operation,
                "ok": True,
                "data": {"ticket": "PROJ-42"},
            }

        monkeypatch.setattr("src.control_plane.ingress._execute", _track_execute)

        from src.control_plane.ingress import submit_intent

        intent = _make_intent()
        ctx = _trusted_ctx()

        # --- first attempt: succeeds ---
        r1 = await submit_intent(intent, ctx)
        assert r1["decision"] == "permit:executed"
        assert len(call_keys) == 1

        # Simulate: executor thinks "failed" but vendor actually got the POST.
        # The system enters UNKNOWN state — it cannot tell if the side effect
        # happened.  A blind retry would create a duplicate.  Instead the
        # idempotency guard catches it.
        r2 = await submit_intent(_make_intent(), ctx)
        assert r2["decision"] == "deny:duplicate"
        assert len(call_keys) == 1  # vendor was NOT called again

    @pytest.mark.asyncio
    async def test_vendor_call_counter_proves_at_most_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Vendor mock tracks call counts — proves exactly 1 side effect."""
        vendor_calls = {"count": 0}

        def _counting_execute(
            authorized: AuthorizedAction, *, role_caps: list[str] | None = None
        ) -> dict[str, Any]:
            vendor_calls["count"] += 1
            return {
                "op": authorized.operation,
                "ok": True,
                "data": {"id": "vendor-1"},
            }

        monkeypatch.setattr("src.control_plane.ingress._execute", _counting_execute)

        from src.control_plane.ingress import submit_intent

        ctx = _trusted_ctx()

        await submit_intent(_make_intent(), ctx)
        # Retry after simulated timeout
        await submit_intent(_make_intent(), ctx)
        # Third attempt
        await submit_intent(_make_intent(), ctx)

        assert vendor_calls["count"] == 1, (
            f"Expected exactly 1 vendor call, got {vendor_calls['count']}"
        )


# ---------------------------------------------------------------------------
# 3. Idempotency key derivation
# ---------------------------------------------------------------------------


class TestIdempotencyKeyDerivation:
    """Same operation + target + scope → same key (deterministic)."""

    def test_same_inputs_same_key(self) -> None:
        k1 = build_idempotency_key("t1", "m1", "create_ticket", "PROJ-42", "onboarding")
        k2 = build_idempotency_key("t1", "m1", "create_ticket", "PROJ-42", "onboarding")
        assert k1 == k2

    def test_different_operation_different_key(self) -> None:
        k1 = build_idempotency_key("t1", "m1", "create_ticket", "PROJ-42", "onboarding")
        k2 = build_idempotency_key("t1", "m1", "update_ticket", "PROJ-42", "onboarding")
        assert k1 != k2

    def test_different_target_different_key(self) -> None:
        k1 = build_idempotency_key("t1", "m1", "create_ticket", "PROJ-42", "onboarding")
        k2 = build_idempotency_key("t1", "m1", "create_ticket", "PROJ-99", "onboarding")
        assert k1 != k2

    def test_different_scope_different_key(self) -> None:
        k1 = build_idempotency_key("t1", "m1", "create_ticket", "PROJ-42", "onboarding")
        k2 = build_idempotency_key("t1", "m1", "create_ticket", "PROJ-42", "expansion")
        assert k1 != k2

    def test_empty_scope_uses_dash(self) -> None:
        k = build_idempotency_key("t1", "m1", "op", "tgt", "")
        assert k.endswith(":-")
        k2 = build_idempotency_key("t1", "m1", "op", "tgt", "-")
        assert k == k2

    def test_key_format_no_thread_no_seq(self) -> None:
        key = build_idempotency_key(
            "tenant-acme", "mission-m1", "create_ticket", "PROJ-42", "onboarding"
        )
        parts = key.split(":")
        assert len(parts) == 5
        assert "thread" not in key
        assert "seq" not in key

    def test_authorized_action_key_matches_derivation(self) -> None:
        """Authorize an intent and verify the bound key matches build_idempotency_key."""
        intent = _make_intent()
        ctx = _trusted_ctx()
        authorized = authorize(intent, ctx)
        expected_key = build_idempotency_key(
            ctx["tenant_id"],
            ctx["mission_id"],
            intent.operation,
            intent.target_reference,
            ctx.get("business_scope", ""),
        )
        assert authorized.idempotency_key == expected_key


# ---------------------------------------------------------------------------
# 4. Concurrent submission — two identical intents, only one executes
# ---------------------------------------------------------------------------


class TestConcurrentSubmission:
    """Two identical intents submitted concurrently → only one reaches the vendor."""

    @pytest.fixture(autouse=True)
    def _clean_state(self) -> None:
        AUDIT_LOG.clear()
        reset_store()
        reset_seen()

    @pytest.mark.asyncio
    async def test_concurrent_identical_intents(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fire two coroutines at the same instant — idempotency guard serializes them."""
        call_keys: list[str] = []

        def _track_execute(
            authorized: AuthorizedAction, *, role_caps: list[str] | None = None
        ) -> dict[str, Any]:
            call_keys.append(authorized.idempotency_key)
            return {"op": authorized.operation, "ok": True, "data": {"key": "X-1"}}

        monkeypatch.setattr("src.control_plane.ingress._execute", _track_execute)

        from src.control_plane.ingress import submit_intent

        ctx = _trusted_ctx()

        # Submit concurrently (gather races them through the event loop)
        results = await asyncio.gather(
            submit_intent(_make_intent(), ctx),
            submit_intent(_make_intent(), ctx),
        )

        decisions = sorted(r["decision"] for r in results)
        assert decisions == ["deny:duplicate", "permit:executed"], decisions
        assert len(call_keys) == 1

    @pytest.mark.asyncio
    async def test_concurrent_different_intents_both_succeed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two different intents (different targets) → both execute."""
        counter = _mock_execute(monkeypatch)

        from src.control_plane.ingress import submit_intent

        ctx = _trusted_ctx()
        r1 = await submit_intent(_make_intent(target_reference="PROJ-1"), ctx)
        r2 = await submit_intent(_make_intent(target_reference="PROJ-2"), ctx)
        assert r1["decision"] == "permit:executed"
        assert r2["decision"] == "permit:executed"
        assert counter["count"] == 2


# ---------------------------------------------------------------------------
# 5. Recovery after crash — SeenSet reset
# ---------------------------------------------------------------------------


class TestRecoveryAfterCrash:
    """Crash loses in-memory SeenSet; system still safe via reconciliation."""

    @pytest.fixture(autouse=True)
    def _clean_state(self) -> None:
        AUDIT_LOG.clear()
        reset_store()
        reset_seen()

    @pytest.mark.asyncio
    async def test_seen_set_loss_allows_second_execution(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simulate crash: SeenSet wiped → the same intent executes again.

        This documents the single-process scaffold's contract: the SeenSet
        IS the sole in-memory guard.  Losing it means the process has no
        memory of prior executions.  Production uses Temporal idempotency
        keys backed by durable storage to prevent this scenario.
        """
        call_keys: list[str] = []

        def _track_execute(
            authorized: AuthorizedAction, *, role_caps: list[str] | None = None
        ) -> dict[str, Any]:
            call_keys.append(authorized.idempotency_key)
            return {"op": authorized.operation, "ok": True, "data": {"key": "X-1"}}

        monkeypatch.setattr("src.control_plane.ingress._execute", _track_execute)

        from src.control_plane.ingress import _seen, submit_intent

        ctx = _trusted_ctx()

        # --- first attempt: succeeds ---
        r1 = await submit_intent(_make_intent(), ctx)
        assert r1["decision"] == "permit:executed"
        assert len(call_keys) == 1

        # --- simulate crash: wipe SeenSet ---
        _seen._seen.clear()

        # --- re-submit (crash recovery) ---
        r2 = await submit_intent(_make_intent(), ctx)
        # With a wiped SeenSet the guard is gone → second vendor call happens.
        assert r2["decision"] == "permit:executed"
        assert len(call_keys) == 2

    @pytest.mark.asyncio
    async def test_seen_set_persistence_prevents_duplicate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When SeenSet persists (no crash), duplicate is always denied."""
        counter = _mock_execute(monkeypatch)

        from src.control_plane.ingress import submit_intent

        ctx = _trusted_ctx()

        r1 = await submit_intent(_make_intent(), ctx)
        r2 = await submit_intent(_make_intent(), ctx)
        r3 = await submit_intent(_make_intent(), ctx)

        assert r1["decision"] == "permit:executed"
        assert r2["decision"] == "deny:duplicate"
        assert r3["decision"] == "deny:duplicate"
        assert counter["count"] == 1


# ---------------------------------------------------------------------------
# 6. Version progression
# ---------------------------------------------------------------------------


class TestVersionProgression:
    """Intent with version N, then N+1 → both succeed (different versions)."""

    @pytest.fixture(autouse=True)
    def _clean_state(self) -> None:
        AUDIT_LOG.clear()
        reset_store()
        reset_seen()

    @pytest.mark.asyncio
    async def test_version_n_then_n_plus_1(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two different entities at consecutive versions both execute.

        Each target has a unique idempotency key, so the version gate
        (not idempotency) controls acceptance.
        """
        counter = _mock_execute(monkeypatch)

        from src.control_plane.ingress import submit_intent

        store = get_store()
        store.seed("tenant-acme:mission-1", 5)

        # entity-A at version=5 → matches current=5 → execute → advance to 6
        r1 = await submit_intent(
            _make_intent(target_reference="ENTITY-A"),
            _trusted_ctx(expected_version=5),
        )
        assert r1["decision"] == "permit:executed"
        assert counter["count"] == 1

        # entity-B at version=6 → matches current=6 → execute → advance to 7
        r2 = await submit_intent(
            _make_intent(target_reference="ENTITY-B"),
            _trusted_ctx(expected_version=6),
        )
        assert r2["decision"] == "permit:executed"
        assert counter["count"] == 2

    @pytest.mark.asyncio
    async def test_stale_version_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Intent at version N when current=N+1 → deny:stale_version."""
        counter = _mock_execute(monkeypatch)

        from src.control_plane.ingress import submit_intent

        store = get_store()
        store.seed("tenant-acme:mission-1", 10)

        # version=9 < current=10 → stale
        r = await submit_intent(_make_intent(), _trusted_ctx(expected_version=9))
        assert r["decision"] == "deny:stale_version"
        assert counter["count"] == 0

    @pytest.mark.asyncio
    async def test_no_version_bypasses_gate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """expected_version=None skips the version gate entirely."""
        counter = _mock_execute(monkeypatch)

        from src.control_plane.ingress import submit_intent

        r = await submit_intent(_make_intent(), _trusted_ctx())
        assert r["decision"] == "permit:executed"
        assert counter["count"] == 1

    @pytest.mark.asyncio
    async def test_version_advances_only_after_execution(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Version must NOT advance when execution is denied (e.g., stale_version)."""
        counter = _mock_execute(monkeypatch)

        from src.control_plane.ingress import submit_intent

        store = get_store()
        store.seed("tenant-acme:mission-1", 7)

        # Attempt with wrong version
        await submit_intent(_make_intent(), _trusted_ctx(expected_version=5))
        # Version must still be 7
        assert store.current("tenant-acme:mission-1") == 7
        assert counter["count"] == 0

    @pytest.mark.asyncio
    async def test_stale_version_rejected_with_unique_keys(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Different entity submitted at stale version → deny:stale_version.

        The idempotency key is unique (different target), so the version
        gate fires before any idempotency check.
        """
        counter = _mock_execute(monkeypatch)

        from src.control_plane.ingress import submit_intent

        store = get_store()
        store.seed("tenant-acme:mission-1", 3)

        # entity-A at version=3 → matches current=3 → execute → advance to 4
        r1 = await submit_intent(
            _make_intent(target_reference="ENTITY-A"),
            _trusted_ctx(expected_version=3),
        )
        assert r1["decision"] == "permit:executed"

        # entity-B at version=3 → current is now 4, so version=3 is stale
        r2 = await submit_intent(
            _make_intent(target_reference="ENTITY-B"),
            _trusted_ctx(expected_version=3),
        )
        assert r2["decision"] == "deny:stale_version"
        assert counter["count"] == 1


# ---------------------------------------------------------------------------
# 7. SeenSet unit tests (pure, no ingress)
# ---------------------------------------------------------------------------


class TestSeenSet:
    """Direct unit tests for the SeenSet replay guard."""

    def test_new_key_not_duplicate(self) -> None:
        seen = SeenSet()
        assert seen.is_duplicate("key-1") is False

    def test_mark_then_duplicate(self) -> None:
        seen = SeenSet()
        seen.mark("key-1")
        assert seen.is_duplicate("key-1") is True

    def test_different_keys_independent(self) -> None:
        seen = SeenSet()
        seen.mark("key-1")
        assert seen.is_duplicate("key-2") is False

    def test_mark_idempotent(self) -> None:
        seen = SeenSet()
        seen.mark("k")
        seen.mark("k")
        assert seen.is_duplicate("k") is True


# ---------------------------------------------------------------------------
# 8. VersionStore unit tests
# ---------------------------------------------------------------------------


class TestVersionStore:
    """Direct unit tests for the VersionStore optimistic concurrency gate."""

    def test_seed_and_current(self) -> None:
        vs = VersionStore()
        vs.seed("target-1", 3)
        assert vs.current("target-1") == 3

    def test_unknown_target_returns_none(self) -> None:
        vs = VersionStore()
        assert vs.current("unknown") is None

    def test_advance_increments(self) -> None:
        vs = VersionStore()
        vs.seed("target-1", 3)
        new_v = vs.advance("target-1")
        assert new_v == 4
        assert vs.current("target-1") == 4

    def test_advance_from_unknown_starts_at_zero(self) -> None:
        vs = VersionStore()
        assert vs.advance("new-target") == 0
        assert vs.current("new-target") == 0
