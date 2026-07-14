"""Control Plane tests — pure Python, zero infra."""
import pytest
from pydantic import ValidationError

from src.schemas.control_plane import (
    PolicyDecision,
    RiskScanResult,
    AgentRegistration,
    AuditEvent,
    RiskFlag,
    RiskSeverity,
)
from src.control_plane.registry import ControlPlaneRegistry
from src.control_plane.policy import PolicyEngine
from src.agents.authority_manifest import AgentAuthority


class TestPolicyDecisionSchema:
    def test_valid_policy_decision(self):
        d = PolicyDecision(
            data_classification="internal",
            allowed_model_classes=["gpt-4o"],
            requires_human_approval=False,
            blocked_reason=None,
            approved_tools=["flag_churn_risk_customer"],
        )
        assert d.data_classification == "internal"
        assert d.allowed_model_classes == ["gpt-4o"]
        assert d.requires_human_approval is False
        assert d.approved_tools == ["flag_churn_risk_customer"]

    def test_external_facing_forces_approval(self):
        d = PolicyDecision(
            data_classification="external_investor",
            allowed_model_classes=["gpt-4o"],
            requires_human_approval=True,
            blocked_reason="external_facing_output",
            approved_tools=["draft_investor_update"],
        )
        assert d.requires_human_approval is True
        assert d.blocked_reason == "external_facing_output"

    def test_blocked_decision(self):
        d = PolicyDecision(
            data_classification="restricted",
            allowed_model_classes=[],
            requires_human_approval=True,
            blocked_reason="data_classification_restricted",
            approved_tools=[],
        )
        assert d.blocked_reason == "data_classification_restricted"
        assert d.approved_tools == []


class TestRiskScanResultSchema:
    def test_clean_scan(self):
        r = RiskScanResult(
            status="pass",
            flags=[],
            severity="low",
            recommended_action="proceed",
        )
        assert r.status == "pass"
        assert r.severity == "low"

    def test_flagged_scan(self):
        r = RiskScanResult(
            status="flag",
            flags=[
                RiskFlag(
                    rule_id="R001",
                    description="Contains unsupported growth claim",
                    severity="high",
                    matched_text="growing 300% MoM",
                )
            ],
            severity="high",
            recommended_action="block",
        )
        assert r.status == "flag"
        assert len(r.flags) == 1
        assert r.flags[0].rule_id == "R001"
        assert r.recommended_action == "block"


class TestAgentRegistrationSchema:
    def test_valid_registration(self):
        a = AgentRegistration(
            agent_name="FP&A",
            role="Finance specialist",
            domain="finance",
            allowed_tools=["pause_failed_payment_retry"],
            allowed_models=["gpt-4o-mini"],
            escalation_tier="review",
            external_facing=False,
            data_classification="internal",
            health_status="healthy",
        )
        assert a.agent_name == "FP&A"
        assert a.health_status == "healthy"

    def test_external_facing_registration(self):
        a = AgentRegistration(
            agent_name="Chief of Staff",
            role="manager/cofounder",
            domain="cofounder",
            allowed_tools=["draft_investor_update"],
            allowed_models=["gpt-4o"],
            escalation_tier="approve",
            external_facing=True,
            data_classification="external_investor",
            health_status="healthy",
        )
        assert a.external_facing is True
        assert a.escalation_tier == "approve"

    def test_invalid_domain(self):
        with pytest.raises(ValidationError):
            AgentRegistration(
                agent_name="BadAgent",
                role="hacker",
                domain="unknown",
                allowed_tools=[],
                allowed_models=[],
                escalation_tier="auto",
                external_facing=False,
                data_classification="internal",
                health_status="healthy",
            )


class TestAuditEventSchema:
    def test_audit_event_creation(self):
        e = AuditEvent(
            agent_name="FP&A",
            action="tool_execution",
            tool_name="pause_failed_payment_retry",
            model_used="gpt-4o-mini",
            policy_decision=PolicyDecision(
                data_classification="internal",
                allowed_model_classes=["gpt-4o-mini"],
                requires_human_approval=False,
                blocked_reason=None,
                approved_tools=["pause_failed_payment_retry"],
            ),
            approval_state="auto",
            outcome="completed",
            tenant_id="test-tenant",
        )
        assert e.agent_name == "FP&A"
        assert e.outcome == "completed"


class TestControlPlaneRegistry:
    def test_register_and_get_agent(self):
        registry = ControlPlaneRegistry()
        reg = AgentRegistration(
            agent_name="TestAgent",
            role="tester",
            domain="ops",
            allowed_tools=[],
            allowed_models=["gpt-4o-mini"],
            escalation_tier="auto",
            external_facing=False,
            data_classification="internal",
            health_status="healthy",
        )
        registry.register(reg)
        fetched = registry.get("TestAgent")
        assert fetched is not None
        assert fetched.agent_name == "TestAgent"

    def test_unregistered_agent_returns_none(self):
        registry = ControlPlaneRegistry()
        assert registry.get("GhostAgent") is None

    def test_agent_must_register_with_control_plane(self):
        registry = ControlPlaneRegistry()
        reg = AgentRegistration(
            agent_name="FP&A",
            role="Finance specialist",
            domain="finance",
            allowed_tools=["pause_failed_payment_retry"],
            allowed_models=["gpt-4o-mini"],
            escalation_tier="review",
            external_facing=False,
            data_classification="internal",
            health_status="healthy",
        )
        registry.register(reg)

        assert registry.is_registered("FP&A") is True
        assert registry.is_registered("GhostAgent") is False
        assert registry.is_action_allowed("FP&A", "pause_failed_payment_retry") is True
        assert registry.is_action_allowed("FP&A", "draft_investor_update") is False

    def test_list_agents(self):
        registry = ControlPlaneRegistry()
        reg = AgentRegistration(
            agent_name="ListTest",
            role="tester",
            domain="ops",
            allowed_tools=[],
            allowed_models=[],
            escalation_tier="auto",
            external_facing=False,
            data_classification="internal",
            health_status="healthy",
        )
        registry.register(reg)
        agents = registry.list_agents()
        assert any(a.agent_name == "ListTest" for a in agents)

    def test_health_status_toggle(self):
        registry = ControlPlaneRegistry()
        reg = AgentRegistration(
            agent_name="HealthTest",
            role="tester",
            domain="ops",
            allowed_tools=[],
            allowed_models=[],
            escalation_tier="auto",
            external_facing=False,
            data_classification="internal",
            health_status="healthy",
        )
        registry.register(reg)
        registry.set_health("HealthTest", "degraded")
        assert registry.get("HealthTest").health_status == "degraded"
        registry.set_health("HealthTest", "unhealthy")
        assert registry.get("HealthTest").health_status == "unhealthy"


class TestPolicyEngine:
    def test_internal_policy_auto(self):
        engine = PolicyEngine()
        reg = AgentRegistration(
            agent_name="OPS Agent",
            role="ops",
            domain="ops",
            allowed_tools=["flag_churn_risk_customer"],
            allowed_models=["gpt-4o-mini"],
            escalation_tier="auto",
            external_facing=False,
            data_classification="internal",
            health_status="healthy",
        )
        decision = engine.evaluate(reg, requested_tool="flag_churn_risk_customer")
        assert decision.requires_human_approval is False
        assert "gpt-4o-mini" in decision.allowed_model_classes

    def test_external_facing_outputs_force_hitl_approve(self):
        engine = PolicyEngine()
        reg = AgentRegistration(
            agent_name="Chief of Staff",
            role="cofounder",
            domain="cofounder",
            allowed_tools=["draft_investor_update"],
            allowed_models=["gpt-4o"],
            escalation_tier="approve",
            external_facing=True,
            data_classification="external_investor",
            health_status="healthy",
        )
        decision = engine.evaluate(reg, requested_tool="draft_investor_update")
        assert decision.requires_human_approval is True
        assert decision.data_classification == "external_investor"

    def test_disallowed_tool_blocked(self):
        engine = PolicyEngine()
        reg = AgentRegistration(
            agent_name="OPS Agent",
            role="ops",
            domain="ops",
            allowed_tools=["flag_churn_risk_customer"],
            allowed_models=["gpt-4o-mini"],
            escalation_tier="auto",
            external_facing=False,
            data_classification="internal",
            health_status="healthy",
        )
        decision = engine.evaluate(reg, requested_tool="draft_investor_update")
        assert "draft_investor_update" not in decision.approved_tools
        assert decision.blocked_reason is not None

    def test_unhealthy_agent_blocked(self):
        engine = PolicyEngine()
        reg = AgentRegistration(
            agent_name="BrokenAgent",
            role="ops",
            domain="ops",
            allowed_tools=["flag_churn_risk_customer"],
            allowed_models=["gpt-4o-mini"],
            escalation_tier="auto",
            external_facing=False,
            data_classification="internal",
            health_status="unhealthy",
        )
        decision = engine.evaluate(reg, requested_tool="flag_churn_risk_customer")
        assert decision.requires_human_approval is True
        assert "unhealthy" in (decision.blocked_reason or "")

    def test_restricted_data_classification_blocks(self):
        engine = PolicyEngine()
        reg = AgentRegistration(
            agent_name="RestrictedAgent",
            role="ops",
            domain="ops",
            allowed_tools=["flag_churn_risk_customer"],
            allowed_models=["gpt-4o-mini"],
            escalation_tier="auto",
            external_facing=False,
            data_classification="restricted",
            health_status="healthy",
        )
        decision = engine.evaluate(reg, requested_tool="flag_churn_risk_customer")
        assert "restricted" in (decision.blocked_reason or "")


class TestExternalFacingHITLEnforcement:
    def test_external_facing_workflow_always_approve(self):
        from src.hitl.manager import HITLManager
        m = HITLManager()
        result = m.route(
            severity="info",
            confidence=0.99,
            is_investor_update=True,
        )
        assert result == "approve"

    def test_external_facing_extended_always_approve(self):
        from src.hitl.manager import HITLManager
        m = HITLManager()
        result = m.route_extended(
            severity="info",
            confidence=0.99,
            approval_required=True,
        )
        assert result == "approve"

    def test_external_facing_overrides_risk_tolerance(self):
        from src.hitl.manager import HITLManager
        m = HITLManager()
        result = m.route_extended(
            severity="info",
            confidence=0.99,
            is_investor_update=True,
            risk_tolerance="aggressive",
        )
        assert result == "approve"


class TestMissionStatePolicyState:
    def test_mission_state_records_update_reason_and_policy_state(self):
        from src.session.mission_state import MissionState

        state = MissionState(
            tenant_id="test-tenant",
            last_updated_by="FP&A",
            last_update_reason="Payment retry alert triggered",
            last_changed_fields=["burn_alert", "burn_severity"],
        )
        assert state.last_updated_by == "FP&A"
        assert state.last_update_reason == "Payment retry alert triggered"
        assert "burn_alert" in state.last_changed_fields

    def test_mission_state_policy_state_field(self):
        from src.session.mission_state import MissionState
        from src.schemas.control_plane import PolicyDecision

        state = MissionState(tenant_id="test-tenant")
        state.policy_state = PolicyDecision(
            data_classification="internal",
            allowed_model_classes=["gpt-4o-mini"],
            requires_human_approval=False,
            blocked_reason=None,
            approved_tools=[],
        )
        assert state.policy_state is not None
        assert state.policy_state.data_classification == "internal"

    def test_mission_state_active_agent_roles(self):
        from src.session.mission_state import MissionState

        state = MissionState(
            tenant_id="test-tenant",
            active_agent_roles=["Finance specialist", "Ops specialist"],
        )
        assert "Finance specialist" in state.active_agent_roles
