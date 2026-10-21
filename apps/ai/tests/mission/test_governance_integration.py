"""Governance integration tests — policy gating + governed writes + verify.

Level-2 risk classification (LOW/MEDIUM/HIGH/CRITICAL) maps deterministically
to PolicyDecision ALLOW / REVIEW / BLOCK. HIGH → mandatory human approval;
CRITICAL → block (PolicyViolationError). Verify rejection produces an
ActionResult with verified=False + rollback metadata.
"""

from __future__ import annotations

import asyncio

import pytest

from src.decision.contracts import DecisionAnalysis, ReadinessTier
from src.entities.models import ActionResult
from src.mission import capability_ops
from src.mission.capability_ops import CapabilityOpRegistry
from src.mission.employee_role_config import EmployeeRoleConfig
from src.mission.employee_runtime import EmployeeRuntime, PlanStep, StepPattern
from src.mission.policy_bridge import classify_risk, requires_approval
from src.mission.verify import VerifyOutcome, build_action_result, verify_write
from src.mission.skill_contracts import SkillDefinition, SkillInput, SkillOutput
from src.mission.skill_registry import SkillRegistry
from src.policy.runtime import (
    DefaultPolicyRuntime,
    PolicyDecision,
    PolicyViolationError,
)


class _In(SkillInput):
    """Stub input."""


class _Out(SkillOutput):
    """Stub output."""


def _analysis(confidence: float, decision_id: str = "d-1") -> DecisionAnalysis:
    return DecisionAnalysis(
        decision_id=decision_id,
        tenant_id="t1",
        workspace_id="w-1",
        recommended_option_id="opt-1",
        confidence=confidence,
        readiness=ReadinessTier.PUBLISH if confidence >= 0.8 else ReadinessTier.REVIEW,
    )


def _role(*skills) -> EmployeeRoleConfig:
    return EmployeeRoleConfig(
        role_id="testrole",
        role="Test Role",
        goals=["test"],
        skills=list(skills),
        capabilities=["salesforce.read", "salesforce.update"],
        permissions=["read", "write"],
        policies=["policy.risk"],
        authority={"approve": ["founder"]},
        risk_threshold="MEDIUM",
        kpis=[],
        memory_namespace="testrole",
        mission_types=["test_mission"],
        persona="test",
    )


class TestPolicyGating:
    async def test_policy_evaluate_permit_record_gating(self):
        """evaluate → permit → record maps confidence to ALLOW/REVIEW/BLOCK deterministically."""
        policy = DefaultPolicyRuntime()

        allow = await policy.evaluate(_analysis(0.9), tenant_id="t1")
        assert allow.decision == PolicyDecision.ALLOW
        permitted = await policy.permit("execute", "d-1", tenant_id="t1")
        assert permitted.decision == PolicyDecision.ALLOW
        recorded = await policy.record(permitted, tenant_id="t1")
        assert recorded.decision == PolicyDecision.ALLOW

        review = await policy.evaluate(_analysis(0.5, "d-2"), tenant_id="t1")
        assert review.decision == PolicyDecision.REVIEW

        blocked = await policy.evaluate(_analysis(0.1, "d-3"), tenant_id="t1")
        assert blocked.decision == PolicyDecision.BLOCK
        with pytest.raises(PolicyViolationError):
            await policy.permit("execute", "d-3", tenant_id="t1")

    async def test_high_risk_emits_approval_request(self):
        """A HIGH-risk step emits hitl-approval and waits for the human decision."""
        async def run(ctx, inp) -> _Out:
            return _Out(done=True)

        SkillRegistry.register(
            SkillDefinition(
                name="stub-high",
                description="high-risk stub",
                input_model=_In,
                output_model=_Out,
                run=run,
                uses_llm=False,
                capability_ops=[],
                agentic=False,
            )
        )
        runtime = EmployeeRuntime(tenant_id="t1")
        handler = runtime.signal_handler
        role = _role("stub-high")
        plan = [
            PlanStep(
                pattern=StepPattern.SEQUENTIAL,
                skill="stub-high",
                id="1",
                params={"risk_tier": "HIGH"},
            ),
        ]
        task = asyncio.create_task(runtime.run_plan(plan, role))
        for _ in range(200):
            if handler.emitted:
                break
            await asyncio.sleep(0.01)
        assert handler.emitted, "HIGH-risk step never emitted an approval request"
        assert handler.emitted[0][0] == "hitl-approval"
        handler.resolve({"approved": True, "decision": "approved"})
        result = await task
        assert result.status != "failed"

    async def test_critical_risk_blocked_no_execution(self):
        """A CRITICAL-risk step is blocked before any skill runs."""
        ran: list[str] = []

        async def run(ctx, inp) -> _Out:
            ran.append("stub-critical")
            return _Out(done=True)

        SkillRegistry.register(
            SkillDefinition(
                name="stub-critical",
                description="critical stub",
                input_model=_In,
                output_model=_Out,
                run=run,
                uses_llm=False,
                capability_ops=[],
                agentic=False,
            )
        )
        runtime = EmployeeRuntime(tenant_id="t1")
        role = _role("stub-critical")
        plan = [
            PlanStep(
                pattern=StepPattern.SEQUENTIAL,
                skill="stub-critical",
                id="1",
                params={"risk_tier": "CRITICAL"},
            ),
        ]
        result = await runtime.run_plan(plan, role)
        assert ran == []
        assert result.status == "failed"


class TestRiskClassification:
    def test_classify_risk_from_step_and_role(self):
        """classify_risk honours explicit risk_tier then falls back to role threshold."""
        role = _role()
        assert classify_risk({"risk_tier": "HIGH"}, role) == "HIGH"
        assert classify_risk({}, role) == "MEDIUM"  # role default

    def test_requires_approval_for_high(self):
        """HIGH and CRITICAL always require approval; LOW/MEDIUM do not."""
        role = _role()
        assert requires_approval({"risk_tier": "HIGH"}, role) is True
        assert requires_approval({"risk_tier": "CRITICAL"}, role) is True
        assert requires_approval({"risk_tier": "LOW"}, role) is False
        assert requires_approval({}, role) is False


class TestVerifyRejection:
    def test_verify_rejection_produces_actionresult_verified_false(self):
        """A rejected verify maps to ActionResult(verified=False) + rollback metadata."""
        outcome = VerifyOutcome(
            verified=False,
            verified_by="EmployeeRuntime.verify",
            rollback_metadata={
                "capability": "salesforce.update",
                "record_id": "d-1",
                "reason": "read-back mismatch",
            },
            mismatch="stage",
        )
        action_result: ActionResult = build_action_result("act-1", outcome)
        assert action_result.verified is False
        assert action_result.rollback_metadata["record_id"] == "d-1"
        assert action_result.verified_by == "EmployeeRuntime.verify"

    async def test_verify_write_detects_mismatch(self, monkeypatch):
        """verify_write read-back mismatch yields verified=False with rollback metadata."""

        class MockCap:
            def get_deals(self):
                return [{"id": "d-1", "stage": "discovery"}]  # stale — write was lost

            def get_customers(self):
                return []

            def update_deal(self, deal_id, fields):
                return {"id": deal_id, "stage": "discovery"}

            def get_messages(self, channel, **filters):
                return []

            def send_message(self, channel, text):
                return {"ok": True}

            def get_issues(self, **filters):
                return []

            def create_issue(self, data):
                return "X-1"

            def update_issue(self, issue_id, fields):
                return {"ok": True}

            def get_pages(self, **filters):
                return []

            def update_page(self, page_id, data):
                return {"ok": True}

        monkeypatch.setattr(capability_ops, "_resolve_capability", lambda name, config: MockCap())
        outcome = await verify_write(
            "salesforce.update",
            {"record_id": "d-1", "fields": {"stage": "closing"}},
            {"stage": "closing"},
            "t1",
            capabilities=CapabilityOpRegistry,
        )
        assert outcome.verified is False
        assert outcome.rollback_metadata


class TestGovernedWrites:
    def test_governed_write_decorator_applied_to_write_ops(self):
        """Write ops are routed through @governed_write (functools-wrapped)."""
        for name in CapabilityOpRegistry.write_ops():
            op = CapabilityOpRegistry.get(name)
            assert op.governed is True
            # The underlying execute closure is decorated by governed_write:
            assert getattr(op.execute, "__wrapped__", None) is not None