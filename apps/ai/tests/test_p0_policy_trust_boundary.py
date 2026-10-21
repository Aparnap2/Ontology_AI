"""P0 RED: policy must not read risk from the untrusted intent body.

Threat model
------------
``policy.classify`` / ``needs_approval`` / ``is_blocked`` decide whether a
human must approve and whether execution is blocked outright. Those
decisions are security controls.

Vulnerability
-------------
``classify`` built its parameter dict as::

    params = {"risk_tier": getattr(intent, "risk_tier", None)}
    params.update(intent.requested_parameters)

``ActionIntent`` has no ``risk_tier`` field (``extra="forbid"``), so the
first read is always ``None`` — and the second line lets the *untrusted*
``requested_parameters`` payload supply it. A prompt-injected planner can
therefore set ``requested_parameters["risk_tier"] = "LOW"`` and bypass both
the HIGH/CRITICAL approval gate and the CRITICAL execution block in one move.

Required behaviour
------------------
* risk tier derives from TRUSTED state only (role_config.risk_threshold,
  or canonical per-operation metadata) — never from the intent body
* an intent-supplied risk_tier is ignored, whatever its value
* HIGH/CRITICAL trusted tiers still require approval
* CRITICAL trusted tier still blocks execution
"""

from __future__ import annotations

import pytest

from src.control_plane import policy as policy_mod
from src.control_plane.contracts import ActionIntent
from src.mission.employee_role_config import EmployeeRoleConfig


def _intent(parameters: dict | None = None) -> ActionIntent:
    return ActionIntent(
        capability="vendor",
        operation="vendor_ticket.create",
        target_reference="vendor-acme-001",
        requested_parameters=parameters if parameters is not None else {},
        reason="incident escalation",
        evidence_ids=["ev-1"],
        expected_outcome="ticket created",
        confidence=0.9,
        requested_by="untrusted-planner",
    )


def _role(threshold: str) -> EmployeeRoleConfig:
    return EmployeeRoleConfig(
        role_id="r1",
        role="it_ops",
        capabilities=["vendor_ticket.create"],
        permissions=[],
        risk_threshold=threshold,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# 1. An intent-supplied risk_tier must be ignored entirely
# ---------------------------------------------------------------------------


class TestIntentSuppliedRiskTierIgnored:
    @pytest.mark.parametrize("claimed", ["LOW", "MEDIUM", "HIGH", "CRITICAL", "low"])
    def test_claimed_tier_never_influences_classification(self, claimed: str) -> None:
        """Whatever the model claims, the trusted threshold decides."""
        trusted_tier = "CRITICAL"
        role = _role(trusted_tier)

        effective = policy_mod.classify(_intent({"risk_tier": claimed}), role)

        assert effective == trusted_tier, (
            f"intent claimed {claimed!r} but effective tier was {effective!r}; "
            "untrusted input must not reach risk classification"
        )

    def test_low_claim_cannot_bypass_approval_gate(self) -> None:
        """The exact injection: claim LOW, trusted tier is HIGH."""
        role = _role("HIGH")

        assert policy_mod.needs_approval(_intent({"risk_tier": "LOW"}), role) is True, (
            "a prompt-injected risk_tier=LOW bypassed the human approval gate"
        )

    def test_low_claim_cannot_bypass_critical_block(self) -> None:
        role = _role("CRITICAL")

        assert policy_mod.is_blocked(_intent({"risk_tier": "LOW"}), role) is True, (
            "a prompt-injected risk_tier=LOW bypassed the CRITICAL execution block"
        )

    def test_no_role_config_still_ignores_intent_risk_tier(self) -> None:
        """With no role config the tier must not come from the intent either."""
        effective = policy_mod.classify(_intent({"risk_tier": "LOW"}), None)

        assert effective != "LOW", (
            "with no trusted role config the tier must not be taken from the intent"
        )


# ---------------------------------------------------------------------------
# 2. Trusted tiers still drive approval and blocking
# ---------------------------------------------------------------------------


class TestTrustedTiersStillGovern:
    def test_high_trusted_tier_requires_approval(self) -> None:
        assert policy_mod.needs_approval(_intent(), _role("HIGH")) is True

    def test_critical_trusted_tier_blocks(self) -> None:
        assert policy_mod.is_blocked(_intent(), _role("CRITICAL")) is True

    def test_low_trusted_tier_needs_no_approval(self) -> None:
        assert policy_mod.needs_approval(_intent(), _role("LOW")) is False

    def test_low_trusted_tier_does_not_block(self) -> None:
        assert policy_mod.is_blocked(_intent(), _role("LOW")) is False


# ---------------------------------------------------------------------------
# 3. The exploit chain, end to end through ingress
# ---------------------------------------------------------------------------


class TestComposedEscalationBlocked:
    async def test_injected_low_tier_cannot_reach_execution_unapproved(self) -> None:
        """risk_tier=LOW + unauthorized op -> denied before any execution."""
        from src.control_plane.ingress import submit_intent

        intent = ActionIntent(
            capability="jira",
            operation="jira.create",  # NOT in the allowlist
            target_reference="PROJ-1",
            requested_parameters={"risk_tier": "LOW", "summary": "exfiltrate"},
            reason="prompt injection attempt",
            evidence_ids=[],
            expected_outcome="issue created",
            confidence=1.0,
            requested_by="injected-planner",
        )
        trusted = {
            "tenant_id": "t1",
            "mission_id": "m-1",
            "employee_id": "emp-1",
            "actor_identity": "system",
            "permissions": ["vendor_ticket.create"],
        }

        result = await submit_intent(intent, trusted)

        assert result["decision"].startswith("deny"), (
            f"composed escalation was not denied: {result['decision']!r}"
        )
        assert "permit:executed" not in result["decision"]
        assert result["verified"] is False
