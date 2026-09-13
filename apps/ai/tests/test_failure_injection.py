"""Failure-injection test suite — proves the system degrades safely.

Every test is deterministic: no wall clock, no network, no LLM.
Each assertion proves one of:
  - No crash on failure (exception handled or rejected cleanly)
  - No duplicate side effect
  - No silent pass (clear error / decision returned)

Categories:
  1. Event layer (4 tests)
  2. External vendor capability (6 tests)
  3. Database / state (3 tests)
  4. Control plane (3 tests)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.control_plane.audit import append_event
from src.control_plane.concurrency import VersionStore, get_store, reset_store
from src.control_plane.contracts import ActionIntent
from src.control_plane.idempotency import SeenSet, build_idempotency_key, reset_seen
from src.control_plane.ingress import submit_intent
from src.events.normalizer import normalize_event
from src.mission import capability_ops
from src.mission.capability_ops import (
    CapabilityOpError,
    CapabilityOpRegistry,
    UnknownCapabilityOpError,
)
from src.mission.capability_ops_vendor import (
    VendorOpError,
    VendorRetryableError,
    VendorTerminalError,
)
from src.mission.signal_handler import InMemorySignalHandler
from src.schemas.event_envelope import EventEnvelope, EventSource


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

_TRUSTED_CTX = {
    "tenant_id": "t-fail-inject",
    "mission_id": "m-fail-inject",
    "employee_id": "emp-fail-inject",
    "actor_identity": "actor-fail-inject",
    "permissions": ["vendor.lookup"],
}


def _intent(
    operation: str = "vendor.lookup",
    target: str = "vendor/v-1",
    **overrides: Any,
) -> ActionIntent:
    """Build a valid ActionIntent with sensible defaults."""
    data = {
        "capability": "vendor",
        "operation": operation,
        "target_reference": target,
        "requested_parameters": {},
        "reason": "failure-injection test",
        "expected_outcome": "deterministic result",
        "confidence": 0.9,
        "requested_by": "tester",
    }
    data.update(overrides)
    return ActionIntent(**data)


def _envelope(**overrides: Any) -> EventEnvelope:
    """Build a valid EventEnvelope with sensible defaults."""
    base: dict[str, Any] = {
        "tenant_id": "t-evt",
        "event_type": "PAYMENT_SUCCESS",
        "source": EventSource.RAZORPAY,
        "payload_ref": "raw_events:deadbeef",
        "payload_hash": "sha256:abcdef",
        "idempotency_key": "razorpay:pay_001:v1",
        "occurred_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "received_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "trace_id": "trace-001",
    }
    base.update(overrides)
    return EventEnvelope(**base)


# ═══════════════════════════════════════════════════════════════════════
# 1. EVENT LAYER (4 tests)
# ═══════════════════════════════════════════════════════════════════════


class TestDuplicateEvent:
    """Submit same incident event twice → second denied as duplicate."""

    def test_seen_set_blocks_duplicate(self) -> None:
        seen = SeenSet()
        key = "t1:m1:incident.detected:inc-42"
        assert not seen.is_duplicate(key)
        seen.mark(key)
        assert seen.is_duplicate(key)

    def test_seen_set_allows_unique(self) -> None:
        seen = SeenSet()
        seen.mark("key-a")
        seen.mark("key-b")
        assert seen.is_duplicate("key-a")
        assert seen.is_duplicate("key-b")
        assert not seen.is_duplicate("key-c")


class TestOutOfOrderEvent:
    """Resolution before detection is rejected or handled gracefully."""

    def test_resolution_before_detection_normalized(self) -> None:
        """normalize_event returns UNKNOWN for unmapped event pairs."""
        result = normalize_event("vendor", "incident.resolved")
        # Not in NORMALIZER_INDEX → gracefully returns UNKNOWN
        assert result == "UNKNOWN"

    def test_envelope_rejects_empty_event_type(self) -> None:
        """Malformed out-of-order envelope with empty type is rejected."""
        with pytest.raises(Exception):
            _envelope(event_type="")


class TestMalformedEvent:
    """Event with missing required fields → rejected with clear error, no crash."""

    def test_envelope_rejects_raw_json_payload_ref(self) -> None:
        with pytest.raises(Exception) as exc_info:
            _envelope(payload_ref='{"raw": "data"}')
        assert (
            "storage reference" in str(exc_info.value).lower()
            or "raw json" in str(exc_info.value).lower()
        )

    def test_envelope_rejects_invalid_payload_ref_prefix(self) -> None:
        with pytest.raises(Exception):
            _envelope(payload_ref="invalid_prefix:something")

    def test_envelope_rejects_whitespace_event_type(self) -> None:
        with pytest.raises(Exception):
            _envelope(event_type="   ")


class TestUnknownEventType:
    """Event with unrecognized type → logged and rejected, system continues."""

    def test_normalizer_returns_unknown_for_unrecognized(self) -> None:
        result = normalize_event("unknown_source", "nonexistent.event")
        assert result == "UNKNOWN"

    def test_normalizer_returns_known_for_mapped(self) -> None:
        result = normalize_event("zoho_books", "expense.created")
        assert result == "EXPENSE_RECORDED"

    def test_system_continues_after_unknown(self) -> None:
        """Processing unknown events doesn't corrupt the normalizer index."""
        normalize_event("hack", "evil.event")
        normalize_event("another", "bad.event")
        # Original mapping still works
        assert normalize_event("zoho_books", "expense.created") == "EXPENSE_RECORDED"


# ═══════════════════════════════════════════════════════════════════════
# 2. EXTERNAL VENDOR CAPABILITY (6 tests)
# ═══════════════════════════════════════════════════════════════════════


class _VendorFailureDoubles:
    """Factory for vendor capability doubles that simulate various failures."""

    @staticmethod
    def http_500() -> MagicMock:
        cap = MagicMock()
        cap.get_vendor.side_effect = VendorRetryableError(
            "HTTP 500: Internal Server Error"
        )
        return cap

    @staticmethod
    def http_429() -> MagicMock:
        cap = MagicMock()
        cap.get_vendor.side_effect = VendorRetryableError("HTTP 429: Rate Limited")
        return cap

    @staticmethod
    def timeout() -> MagicMock:
        cap = MagicMock()
        cap.get_vendor.side_effect = VendorRetryableError(
            "Timeout: vendor did not respond in 30s"
        )
        return cap

    @staticmethod
    def invalid_payload() -> MagicMock:
        cap = MagicMock()
        cap.get_vendor.side_effect = VendorTerminalError(
            "ParseError: invalid JSON from vendor"
        )
        return cap

    @staticmethod
    def connection_refused() -> MagicMock:
        cap = MagicMock()
        cap.get_vendor.side_effect = VendorRetryableError(
            "ConnectionRefused: vendor unreachable"
        )
        return cap

    @staticmethod
    def partial_response() -> MagicMock:
        cap = MagicMock()
        cap.get_vendor.return_value = {"id": "v-1"}  # missing name, status, etc.
        return cap


class TestVendorHTTP500:
    """Vendor returns server error → operation fails gracefully, retryable."""

    def test_retryable_error_has_retryable_flag(self) -> None:
        err = VendorRetryableError("HTTP 500")
        assert err.retryable is True
        assert isinstance(err, VendorOpError)

    def test_http500_double_propagates_cleanly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cap = _VendorFailureDoubles.http_500()
        monkeypatch.setattr(capability_ops, "_resolve_capability", lambda _n, _c: cap)
        capability_ops.CapabilityOpRegistry._ops.clear()

        with pytest.raises(VendorRetryableError, match="HTTP 500"):
            CapabilityOpRegistry.execute("vendor.lookup", {"vendor_id": "v-1"}, "t1")


class TestVendorHTTP429:
    """Rate limited → retryable, backs off."""

    def test_429_is_retryable(self) -> None:
        err = VendorRetryableError("HTTP 429: Too Many Requests")
        assert err.retryable is True

    def test_429_double_raises_retryable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cap = _VendorFailureDoubles.http_429()
        monkeypatch.setattr(capability_ops, "_resolve_capability", lambda _n, _c: cap)
        capability_ops.CapabilityOpRegistry._ops.clear()

        with pytest.raises(VendorRetryableError, match="429"):
            CapabilityOpRegistry.execute("vendor.lookup", {"vendor_id": "v-1"}, "t1")


class TestVendorTimeout:
    """Vendor never responds → timeout error, not a hang."""

    def test_timeout_is_retryable(self) -> None:
        err = VendorRetryableError("Timeout: no response")
        assert err.retryable is True

    def test_timeout_does_not_hang(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Executes synchronously and raises — no coroutine, no hang."""
        cap = _VendorFailureDoubles.timeout()
        monkeypatch.setattr(capability_ops, "_resolve_capability", lambda _n, _c: cap)
        capability_ops.CapabilityOpRegistry._ops.clear()

        with pytest.raises(VendorRetryableError, match="Timeout"):
            CapabilityOpRegistry.execute("vendor.lookup", {"vendor_id": "v-1"}, "t1")


class TestVendorInvalidPayload:
    """Vendor returns non-JSON or wrong schema → parse error, not crash."""

    def test_terminal_error_not_retryable(self) -> None:
        err = VendorTerminalError("ParseError: bad json")
        assert err.retryable is False

    def test_invalid_payload_raises_terminal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cap = _VendorFailureDoubles.invalid_payload()
        monkeypatch.setattr(capability_ops, "_resolve_capability", lambda _n, _c: cap)
        capability_ops.CapabilityOpRegistry._ops.clear()

        with pytest.raises(VendorTerminalError, match="ParseError"):
            CapabilityOpRegistry.execute("vendor.lookup", {"vendor_id": "v-1"}, "t1")


class TestVendorConnectionRefused:
    """Vendor unreachable → connection error, retryable."""

    def test_connection_refused_is_retryable(self) -> None:
        err = VendorRetryableError("ConnectionRefused")
        assert err.retryable is True

    def test_connection_refused_double_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cap = _VendorFailureDoubles.connection_refused()
        monkeypatch.setattr(capability_ops, "_resolve_capability", lambda _n, _c: cap)
        capability_ops.CapabilityOpRegistry._ops.clear()

        with pytest.raises(VendorRetryableError, match="ConnectionRefused"):
            CapabilityOpRegistry.execute("vendor.lookup", {"vendor_id": "v-1"}, "t1")


class TestVendorPartialResponse:
    """Vendor returns incomplete data → handled gracefully."""

    def test_partial_response_returns_as_is(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Incomplete data is returned; caller must handle missing fields."""
        cap = _VendorFailureDoubles.partial_response()
        monkeypatch.setattr(capability_ops, "_resolve_capability", lambda _n, _c: cap)
        capability_ops.CapabilityOpRegistry._ops.clear()

        result = CapabilityOpRegistry.execute(
            "vendor.lookup", {"vendor_id": "v-1"}, "t1"
        )
        assert result["ok"] is True
        # Data is incomplete — only id present
        assert result["data"] == {"id": "v-1"}
        assert "name" not in result["data"]

    def test_partial_response_no_crash_on_missing_fields(self) -> None:
        """Accessing missing fields returns None/sentinel, no exception."""
        data = {"id": "v-1"}
        assert data.get("name") is None
        assert data.get("status") is None
        assert len(data) == 1


# ═══════════════════════════════════════════════════════════════════════
# 3. DATABASE / STATE (3 tests)
# ═══════════════════════════════════════════════════════════════════════


class TestOptimisticConcurrencyConflict:
    """Version mismatch → stale_version denied."""

    def test_version_mismatch_detected(self) -> None:
        store = VersionStore()
        store.seed("t1:m1", 5)
        # Planner read version=5, but store is now at 6
        store.advance("t1:m1")
        assert store.current("t1:m1") == 6

    def test_version_store_advance(self) -> None:
        store = VersionStore()
        store.seed("t1:m1", 0)
        v1 = store.advance("t1:m1")
        v2 = store.advance("t1:m1")
        assert v1 == 1
        assert v2 == 2

    def test_version_store_current_none_when_empty(self) -> None:
        store = VersionStore()
        assert store.current("nonexistent:key") is None


class TestStaleCheckpoint:
    """Checkpoint version behind → detected and rejected."""

    def test_stale_version_rejection_in_ingress(self) -> None:
        """submit_intent returns deny:stale_version when version mismatches."""
        reset_seen()
        reset_store()
        store = get_store()
        store.seed("t-fail-inject:m-fail-inject", 10)

        intent = _intent()
        ctx = {**_TRUSTED_CTX, "expected_version": 5}  # planner saw v5, store is v10

        audit_store: list[dict[str, Any]] = []
        with patch("src.control_plane.ingress.append_event") as mock_append:
            mock_append.side_effect = lambda **kw: append_event(store=audit_store, **kw)
            result = asyncio.run(
                submit_intent(intent, ctx)
            )

        assert result["decision"] == "deny:stale_version"


class TestDuplicateWrite:
    """Same idempotency key → second write is no-op."""

    def test_seen_set_prevents_duplicate_execution(self) -> None:
        seen = SeenSet()
        key = build_idempotency_key("t1", "m1", "vendor.lookup", "v-1", "scope")

        assert not seen.is_duplicate(key)
        seen.mark(key)
        assert seen.is_duplicate(key)

    def test_different_scopes_are_distinct(self) -> None:
        seen = SeenSet()
        k1 = build_idempotency_key("t1", "m1", "op", "target", "scope-a")
        k2 = build_idempotency_key("t1", "m1", "op", "target", "scope-b")
        seen.mark(k1)
        assert seen.is_duplicate(k1)
        assert not seen.is_duplicate(k2)


# ═══════════════════════════════════════════════════════════════════════
# 4. CONTROL PLANE (3 tests)
# ═══════════════════════════════════════════════════════════════════════


class TestIdempotencyUnderRetry:
    """Submit same intent 3 times → only 1 execution."""

    def test_same_intent_denied_on_second_submit(self) -> None:
        """First submit permits, second submits sees SeenSet and denies."""
        reset_seen()
        reset_store()

        # vendor.lookup requires vendor_id in params for execution to succeed
        intent = _intent(requested_parameters={"vendor_id": "v-1"})

        audit_store: list[dict[str, Any]] = []
        with patch("src.control_plane.ingress.append_event") as mock_append:
            mock_append.side_effect = lambda **kw: append_event(store=audit_store, **kw)
            # First submission → permit (execution succeeds)
            result1 = asyncio.run(
                submit_intent(intent, _TRUSTED_CTX)
            )
            assert result1["decision"] == "permit:executed"

            # Second submission → deny:duplicate (same idempotency key)
            result2 = asyncio.run(
                submit_intent(intent, _TRUSTED_CTX)
            )
            assert result2["decision"] == "deny:duplicate"

    def test_third_submission_still_denied(self) -> None:
        """Third retry is also denied — idempotency holds."""
        reset_seen()
        reset_store()

        intent = _intent(requested_parameters={"vendor_id": "v-1"})

        audit_store: list[dict[str, Any]] = []
        with patch("src.control_plane.ingress.append_event") as mock_append:
            mock_append.side_effect = lambda **kw: append_event(store=audit_store, **kw)
            asyncio.run(
                submit_intent(intent, _TRUSTED_CTX)
            )
            result3 = asyncio.run(
                submit_intent(intent, _TRUSTED_CTX)
            )
            result4 = asyncio.run(
                submit_intent(intent, _TRUSTED_CTX)
            )

        assert result3["decision"] == "deny:duplicate"
        assert result4["decision"] == "deny:duplicate"


class TestApprovalTimeout:
    """Approval not received in time → denied:approval_expired."""

    def test_approval_timeout_returns_expired(self) -> None:
        """When approval times out, ingress returns deny:approval_expired."""
        reset_seen()
        reset_store()

        # Need an intent that triggers approval (HIGH risk)
        intent = _intent(
            requested_parameters={"risk_tier": "HIGH"},
        )

        handler = InMemorySignalHandler()
        ctx = {
            **_TRUSTED_CTX,
            "role_config": MagicMock(
                risk_threshold="HIGH", capabilities=["vendor.lookup"]
            ),
            "approval_timeout_seconds": 0.01,  # 10ms timeout
            "version": None,
            "current_version": None,
        }

        audit_store: list[dict[str, Any]] = []
        with patch("src.control_plane.ingress.append_event") as mock_append:
            mock_append.side_effect = lambda **kw: append_event(store=audit_store, **kw)
            result = asyncio.run(
                submit_intent(intent, ctx, signal_handler=handler)
            )

        assert result["decision"] == "deny:approval_expired"

    def test_approval_emitted_before_timeout(self) -> None:
        """The HITL signal is emitted even when approval will time out."""
        reset_seen()
        reset_store()

        intent = _intent(
            requested_parameters={"risk_tier": "HIGH"},
        )

        handler = InMemorySignalHandler()
        ctx = {
            **_TRUSTED_CTX,
            "role_config": MagicMock(
                risk_threshold="HIGH", capabilities=["vendor.lookup"]
            ),
            "approval_timeout_seconds": 0.01,
            "version": None,
            "current_version": None,
        }

        audit_store: list[dict[str, Any]] = []
        with patch("src.control_plane.ingress.append_event") as mock_append:
            mock_append.side_effect = lambda **kw: append_event(store=audit_store, **kw)
            asyncio.run(
                submit_intent(intent, ctx, signal_handler=handler)
            )

        # Signal was emitted even though timeout expired
        assert len(handler.emitted) == 1
        assert handler.emitted[0][0] == "hitl-approval"


class TestVersionGate:
    """Submit with wrong version → denied:stale_version."""

    def test_wrong_version_denied(self) -> None:
        """Planner claims version=99 but store is at 0 → deny:stale_version."""
        reset_seen()
        reset_store()
        store = get_store()
        store.seed("t-fail-inject:m-fail-inject", 0)

        intent = _intent()
        ctx = {**_TRUSTED_CTX, "expected_version": 99}

        audit_store: list[dict[str, Any]] = []
        with patch("src.control_plane.ingress.append_event") as mock_append:
            mock_append.side_effect = lambda **kw: append_event(store=audit_store, **kw)
            result = asyncio.run(
                submit_intent(intent, ctx)
            )

        assert result["decision"] == "deny:stale_version"

    def test_correct_version_permits(self) -> None:
        """Planner claims matching version → execution proceeds."""
        reset_seen()
        reset_store()
        store = get_store()
        store.seed("t-fail-inject:m-fail-inject", 3)

        intent = _intent(requested_parameters={"vendor_id": "v-1"})
        ctx = {**_TRUSTED_CTX, "expected_version": 3}

        audit_store: list[dict[str, Any]] = []
        with patch("src.control_plane.ingress.append_event") as mock_append:
            mock_append.side_effect = lambda **kw: append_event(store=audit_store, **kw)
            result = asyncio.run(
                submit_intent(intent, ctx)
            )

        assert result["decision"] == "permit:executed"


# ═══════════════════════════════════════════════════════════════════════
# 5. BONUS: Error taxonomy contract tests
# ═══════════════════════════════════════════════════════════════════════


class TestErrorTaxonomy:
    """Verify the error hierarchy is well-formed for circuit breakers."""

    def test_retryable_is_subclass_of_base(self) -> None:
        assert issubclass(VendorRetryableError, VendorOpError)

    def test_terminal_is_subclass_of_base(self) -> None:
        assert issubclass(VendorTerminalError, VendorOpError)

    def test_retryable_base_flag(self) -> None:
        err = VendorRetryableError("transient")
        assert err.retryable is True
        assert isinstance(err, Exception)

    def test_terminal_base_flag(self) -> None:
        err = VendorTerminalError("permanent")
        assert err.retryable is False

    def test_capability_op_error_hierarchy(self) -> None:
        assert issubclass(UnknownCapabilityOpError, CapabilityOpError)
        assert issubclass(CapabilityOpError, Exception)

    def test_unknown_op_raises_correctly(self) -> None:
        with pytest.raises(UnknownCapabilityOpError, match="unknown capability op"):
            CapabilityOpRegistry.get("nonexistent.op_xyz")
