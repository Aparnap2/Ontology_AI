"""P0 RED: a role must be able to verify its own writes.

Regression introduced by the P0 capability-allowlist fix
(`CapabilityOpRegistry.assert_allowed` now denies on absence).

`verify.py` performs read-back through the READ_COUNTERPART of the op it
wrote (``salesforce.update`` -> ``salesforce.read``, verify.py:28-34). The
role in `tests/mission/test_employee_runtime.py::test_verify_pass` grants
only ``["salesforce.update"]``.

Before the fix the read-back call silently succeeded, because ``None``
role_caps meant "unrestricted". After the fix it is correctly denied, the
exception is swallowed at verify.py:178, and the write reports
NOT_VERIFIED — so a legitimate write looks unverified.

Verified: this test passes at V7 baseline 18f73f1 and fails on the branch.

Two defects, and the fix must address both:

1. The role under test does not grant the read counterpart it needs. A role
   that can write but cannot read cannot verify its own write, so shipped
   configs must pair them (config/employees.yaml already does).

2. ``verify.py`` conflates "the write did not land" with "we were not
   permitted to check". A denied read must surface as an authorization
   failure, never as a silent verification mismatch — otherwise a
   misconfigured role looks like a broken integration.
"""

from __future__ import annotations

import pytest

from src.mission.verify import READ_COUNTERPART


class TestReadCounterpartExists:
    def test_every_write_op_declares_its_read_counterpart(self) -> None:
        """A write op with no declared counterpart cannot be verified."""
        # The ops verify.py can read back. A write op mapped to a read op
        # that is not itself a real capability would fail closed forever.
        from src.mission.capability_ops import CapabilityOpRegistry

        CapabilityOpRegistry._ensure_loaded()
        registered = set(CapabilityOpRegistry._ops)
        for write_op, read_op in READ_COUNTERPART.items():
            if write_op in registered:
                assert read_op in registered, (
                    f"{write_op} declares read-back {read_op!r}, which is not a "
                    "registered capability; verification would always deny"
                )

    def test_write_without_counterpart_is_documented_not_silent(self) -> None:
        """Vendor writes intentionally have no counterpart (fail-closed)."""
        from src.mission.capability_ops import CapabilityOpRegistry

        CapabilityOpRegistry._ensure_loaded()
        write_ops = CapabilityOpRegistry.write_ops()
        unbacked = [op for op in write_ops if op not in READ_COUNTERPART]
        # These must fail closed to INDETERMINATE, never silently "verify".
        assert "vendor_ticket.create" in unbacked, (
            "vendor_ticket.create is expected to have no READ_COUNTERPART"
        )


class TestRoleCanVerifyItsOwnWrite:
    """A role granted a write must also be granted the read to verify it."""

    @pytest.mark.parametrize(
        "write_op,read_op",
        [(w, r) for w, r in READ_COUNTERPART.items()],
    )
    def test_write_implies_granting_its_read(self, write_op: str, read_op: str) -> None:
        from src.mission.capability_ops import CapabilityOpRegistry

        CapabilityOpRegistry._ensure_loaded()
        if write_op not in CapabilityOpRegistry._ops:
            pytest.skip(f"{write_op} is not a registered capability")

        allowlist = [write_op, read_op]
        # Both must be accepted; this is the configuration production uses.
        CapabilityOpRegistry.assert_allowed(write_op, allowlist)
        CapabilityOpRegistry.assert_allowed(read_op, allowlist)

    def test_write_only_role_is_denied_the_read_back(self) -> None:
        """The regression itself: a write-only role cannot verify.

        This is CORRECT fail-closed behaviour. verify.py must therefore
        surface the denial rather than reporting a verification mismatch.
        """
        from src.mission.capability_ops import (
            CapabilityNotAllowedError,
            CapabilityOpRegistry,
        )

        with pytest.raises(CapabilityNotAllowedError):
            CapabilityOpRegistry.assert_allowed("salesforce.read", ["salesforce.update"])


class TestVerificationDistinguishesDeniedFromMismatched:
    """A denied read must NOT be reported as 'the write did not land'."""

    async def test_denied_readback_is_not_silently_not_verified(self) -> None:
        """Either the read is granted, or the failure is explicit.

        The bug under test: verify.py swallowed the authorization error and
        returned state=NOT_VERIFIED with mismatch=None, which is
        indistinguishable from a genuine mismatch.
        """
        from src.mission.capability_ops import CapabilityOpRegistry
        from src.mission.verify import verify_write

        # A read-back the role is NOT permitted to perform.
        try:
            outcome = await verify_write(
                "salesforce.update",
                {"fields": {"Status": "Closed"}},
                {},
                "t1",
                capabilities=CapabilityOpRegistry,
                role_caps=["salesforce.update"],  # write only
                result={"Status": "Closed"},
            )
        except Exception as exc:  # pragma: no cover - acceptable alternative
            # Raising is an acceptable, loud outcome.
            assert "allowlist" in str(exc).lower() or "denied" in str(exc).lower(), (
                f"unexpected error type from a denied read-back: {exc!r}"
            )
            return

        # Returning is acceptable only if it says WHY.
        detail = f"{outcome.state} {getattr(outcome, 'mismatch', None)} {getattr(outcome, 'detail', '')}"
        assert outcome.state != "VERIFIED", (
            "a denied read-back must never report VERIFIED"
        )
        assert "allowlist" in detail.lower() or "denied" in detail.lower() or (
            outcome.state == "INDETERMINATE"
        ), (
            f"a denied read-back reported as {outcome.state!r} with no reason; "
            "authorization failures must be distinguishable from mismatches"
        )