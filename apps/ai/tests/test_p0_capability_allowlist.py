"""P0 RED: the capability registry allowlist must fail CLOSED.

Vulnerability
-------------
``CapabilityOpRegistry.assert_allowed`` returned early when
``role_caps is None``::

    if role_caps is None:
        return

``None`` was therefore treated as "unrestricted" rather than "no
authority". ``execute()`` forwards ``role_caps`` straight from the caller,
and callers legitimately pass ``None`` when no role config is in play — so
omitting a role silently disabled the allowlist entirely.

This is the same class of defect as the control-plane authorization fix: an
absent allowlist is not permission.

The registry is the LAST line of defence. ``authorize()`` already rejects
out-of-scope operations earlier in the chain, but any future caller that
reaches the registry without a populated allowlist would otherwise execute
arbitrary registered ops.

Required behaviour
------------------
* ``role_caps is None``  -> DENY
* ``role_caps == []``    -> DENY
* operation not listed   -> DENY (unchanged)
* operation listed       -> allowed
"""

from __future__ import annotations

import pytest

from src.mission.capability_ops import (
    CapabilityNotAllowedError,
    CapabilityOpRegistry,
)

WRITE_OP = "vendor_ticket.create"
READ_OP = "vendor.lookup"


# ---------------------------------------------------------------------------
# Missing / empty allowlist must deny
# ---------------------------------------------------------------------------


class TestMissingAllowlistFailsClosed:
    def test_none_allowlist_denies(self) -> None:
        with pytest.raises(CapabilityNotAllowedError):
            CapabilityOpRegistry.assert_allowed(WRITE_OP, None)

    def test_empty_allowlist_denies(self) -> None:
        with pytest.raises(CapabilityNotAllowedError):
            CapabilityOpRegistry.assert_allowed(WRITE_OP, [])

    def test_execute_with_none_allowlist_denies(self) -> None:
        with pytest.raises(CapabilityNotAllowedError):
            CapabilityOpRegistry.execute(
                WRITE_OP, {}, "t1", role_caps=None
            )

    def test_execute_with_empty_allowlist_denies(self) -> None:
        with pytest.raises(CapabilityNotAllowedError):
            CapabilityOpRegistry.execute(
                WRITE_OP, {}, "t1", role_caps=[]
            )

    def test_error_message_states_the_absence_is_the_cause(self) -> None:
        """A None allowlist must not be reported as a plain mismatch."""
        with pytest.raises(CapabilityNotAllowedError) as exc:
            CapabilityOpRegistry.assert_allowed(WRITE_OP, None)
        assert "no allowlist" in str(exc.value).lower(), (
            f"unhelpful error for a missing allowlist: {exc.value}"
        )


# ---------------------------------------------------------------------------
# Present allowlist keeps working (no over-blocking)
# ---------------------------------------------------------------------------


class TestExplicitAllowlistStillWorks:
    def test_listed_op_is_allowed(self) -> None:
        CapabilityOpRegistry.assert_allowed(WRITE_OP, [WRITE_OP])

    def test_unlisted_op_still_denied(self) -> None:
        with pytest.raises(CapabilityNotAllowedError):
            CapabilityOpRegistry.assert_allowed(READ_OP, [WRITE_OP])

    def test_read_op_allowed_when_listed(self) -> None:
        CapabilityOpRegistry.assert_allowed(READ_OP, [READ_OP, WRITE_OP])
