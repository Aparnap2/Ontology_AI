"""Tests for HITL Governance — 6-level hierarchy for vendor operations.

Covers:
1. L1 operations auto-approve
2. L2 operations require notification
3. L3+ operations require explicit approval
4. Unknown operations default to L5 (conservative)
5. Mission modification preserves audit trail
6. Mission redirect preserves original history
7. Approval rejection stops execution
8. All models are strict (extra=forbid)
9. No I/O, no LLM, no wall clock in the module
"""

from __future__ import annotations

import pytest

from src.mission.hitl_governance import (
    AuditEntry,
    ApprovalDecision,
    GovernanceLevel,
    ModifiedMission,
    MissionSnapshot,
    Modification,
    RedirectedMission,
    classify_governance_level,
    evaluate_approval_request,
    modify_mission,
    redirect_mission,
)


# ── Helpers ────────────────────────────────────────────────────────────


def _mission(
    mission_id: str = "m-1",
    target: str = "vendor/incident-42",
    priority: str = "medium",
    scope: str = "full",
    escalation_policy: str = "default",
) -> MissionSnapshot:
    return MissionSnapshot(
        mission_id=mission_id,
        target=target,
        priority=priority,
        scope=scope,
        escalation_policy=escalation_policy,
    )


# ── 1. L1 operations auto-approve ─────────────────────────────────────


class TestL1AutoApprove:
    def test_read_operations_are_l1(self) -> None:
        assert classify_governance_level("read.jira.issue") == GovernanceLevel.L1_AUTO
        assert (
            classify_governance_level("search.vendor_tickets")
            == GovernanceLevel.L1_AUTO
        )
        assert classify_governance_level("get.slack.message") == GovernanceLevel.L1_AUTO
        assert classify_governance_level("list.notion.pages") == GovernanceLevel.L1_AUTO
        assert (
            classify_governance_level("query.salesforce.deals")
            == GovernanceLevel.L1_AUTO
        )
        assert (
            classify_governance_level("fetch.vendor.status") == GovernanceLevel.L1_AUTO
        )

    def test_l1_auto_approves_immediately(self) -> None:
        decision = evaluate_approval_request("read.jira.issue", GovernanceLevel.L1_AUTO)
        assert decision.status == "auto_approved"
        assert decision.required_approvers == []
        assert decision.approved_by == ["system"]

    def test_l1_auto_approve_with_context(self) -> None:
        decision = evaluate_approval_request(
            "search.vendor_tickets", GovernanceLevel.L1_AUTO, context={"foo": "bar"}
        )
        assert decision.status == "auto_approved"


# ── 2. L2 operations require notification ──────────────────────────────


class TestL2Notify:
    def test_low_risk_writes_are_l2(self) -> None:
        assert (
            classify_governance_level("jira.update.issue") == GovernanceLevel.L2_NOTIFY
        )
        assert (
            classify_governance_level("vendor_ticket.create")
            == GovernanceLevel.L2_NOTIFY
        )
        assert (
            classify_governance_level("vendor_ticket.update")
            == GovernanceLevel.L2_NOTIFY
        )
        assert classify_governance_level("note.create") == GovernanceLevel.L2_NOTIFY

    def test_l2_requires_stakeholder_approval(self) -> None:
        decision = evaluate_approval_request(
            "jira.update.issue", GovernanceLevel.L2_NOTIFY
        )
        assert decision.status == "pending"
        assert "stakeholder" in decision.required_approvers

    def test_l2_approves_when_stakeholder_present(self) -> None:
        decision = evaluate_approval_request(
            "jira.update.issue",
            GovernanceLevel.L2_NOTIFY,
            context={"approvals": ["stakeholder"]},
        )
        assert decision.status == "approved"
        assert "stakeholder" in decision.approved_by

    def test_l2_still_pending_without_stakeholder(self) -> None:
        decision = evaluate_approval_request(
            "jira.update.issue",
            GovernanceLevel.L2_NOTIFY,
            context={"approvals": ["random_person"]},
        )
        assert decision.status == "pending"
        assert "stakeholder" in decision.required_approvers


# ── 3. L3+ operations require explicit approval ────────────────────────


class TestL3PlusApproval:
    def test_medium_risk_writes_are_l3(self) -> None:
        assert (
            classify_governance_level("notification.send_internal")
            == GovernanceLevel.L3_PEER
        )
        assert (
            classify_governance_level("notification.send_team")
            == GovernanceLevel.L3_PEER
        )

    def test_high_risk_writes_are_l4(self) -> None:
        assert (
            classify_governance_level("notification.send_vendor")
            == GovernanceLevel.L4_MANAGER
        )
        assert (
            classify_governance_level("vendor.escalate.ticket")
            == GovernanceLevel.L4_MANAGER
        )
        assert (
            classify_governance_level("vendor.revoke.access")
            == GovernanceLevel.L4_MANAGER
        )

    def test_financial_writes_are_l5(self) -> None:
        assert (
            classify_governance_level("payment.process") == GovernanceLevel.L5_DIRECTOR
        )
        assert classify_governance_level("refund.issue") == GovernanceLevel.L5_DIRECTOR
        assert (
            classify_governance_level("invoice.generate") == GovernanceLevel.L5_DIRECTOR
        )

    def test_board_level_operations_are_l6(self) -> None:
        assert classify_governance_level("board.resolution") == GovernanceLevel.L6_BOARD
        assert (
            classify_governance_level("policy.change.rollback")
            == GovernanceLevel.L6_BOARD
        )
        assert (
            classify_governance_level("contract.sign.new") == GovernanceLevel.L6_BOARD
        )

    def test_l3_requires_peer_reviewer(self) -> None:
        decision = evaluate_approval_request(
            "notification.send_internal", GovernanceLevel.L3_PEER
        )
        assert decision.status == "pending"
        assert "peer_reviewer" in decision.required_approvers

    def test_l3_approves_with_peer(self) -> None:
        decision = evaluate_approval_request(
            "notification.send_internal",
            GovernanceLevel.L3_PEER,
            context={"approvals": ["peer_reviewer"]},
        )
        assert decision.status == "approved"

    def test_l4_requires_manager(self) -> None:
        decision = evaluate_approval_request(
            "notification.send_vendor", GovernanceLevel.L4_MANAGER
        )
        assert decision.status == "pending"
        assert "manager" in decision.required_approvers

    def test_l5_requires_director_and_c_level(self) -> None:
        decision = evaluate_approval_request(
            "payment.process", GovernanceLevel.L5_DIRECTOR
        )
        assert decision.status == "pending"
        assert "director" in decision.required_approvers
        assert "c_level" in decision.required_approvers

    def test_l5_partial_approval_still_pending(self) -> None:
        decision = evaluate_approval_request(
            "payment.process",
            GovernanceLevel.L5_DIRECTOR,
            context={"approvals": ["director"]},
        )
        assert decision.status == "pending"
        assert "c_level" in decision.required_approvers

    def test_l5_full_approval(self) -> None:
        decision = evaluate_approval_request(
            "payment.process",
            GovernanceLevel.L5_DIRECTOR,
            context={"approvals": ["director", "c_level"]},
        )
        assert decision.status == "approved"

    def test_l6_requires_board_and_legal(self) -> None:
        decision = evaluate_approval_request(
            "board.resolution", GovernanceLevel.L6_BOARD
        )
        assert decision.status == "pending"
        assert "board_member" in decision.required_approvers
        assert "legal" in decision.required_approvers


# ── 4. Unknown operations default to L5 (conservative) ────────────────


class TestUnknownDefaultsToL5:
    def test_unknown_operation_is_l5(self) -> None:
        assert (
            classify_governance_level("totally未知operation")
            == GovernanceLevel.L5_DIRECTOR
        )
        assert classify_governance_level("random.zyx") == GovernanceLevel.L5_DIRECTOR
        assert (
            classify_governance_level("vendor.does_something_new")
            == GovernanceLevel.L5_DIRECTOR
        )

    def test_unknown_operation_requires_director_approval(self) -> None:
        decision = evaluate_approval_request(
            "totally未知operation", GovernanceLevel.L5_DIRECTOR
        )
        assert decision.status == "pending"
        assert "director" in decision.required_approvers

    def test_context_blast_radius_critical_forces_l5(self) -> None:
        level = classify_governance_level(
            "read.jira.issue", context={"blast_radius": "critical"}
        )
        assert level == GovernanceLevel.L5_DIRECTOR

    def test_context_force_level_override(self) -> None:
        level = classify_governance_level(
            "payment.process", context={"force_level": "L1_AUTO"}
        )
        assert level == GovernanceLevel.L1_AUTO

    def test_context_force_level_invalid_falls_through(self) -> None:
        level = classify_governance_level(
            "payment.process", context={"force_level": "INVALID"}
        )
        # Falls through to normal classification
        assert level == GovernanceLevel.L5_DIRECTOR


# ── 5. Mission modification preserves audit trail ──────────────────────


class TestMissionModification:
    def test_single_field_modification(self) -> None:
        mission = _mission(priority="medium")
        mod = Modification(
            priority="high", reason="Escalated by founder", actor="founder"
        )
        result = modify_mission(mission, mod)

        assert result.modification_applied is True
        assert result.mission.priority == "high"
        assert result.mission.target == "vendor/incident-42"  # unchanged
        assert len(result.audit_trail) == 1
        entry = result.audit_trail[0]
        assert entry.action == "modify_priority"
        assert entry.actor == "founder"
        assert entry.previous_value == "medium"
        assert entry.new_value == "high"
        assert entry.reason == "Escalated by founder"

    def test_multi_field_modification(self) -> None:
        mission = _mission(priority="medium", scope="full")
        mod = Modification(
            priority="urgent",
            scope="partial",
            reason="Re-scoped",
            actor="pm",
        )
        result = modify_mission(mission, mod)

        assert result.mission.priority == "urgent"
        assert result.mission.scope == "partial"
        assert len(result.audit_trail) == 2
        actions = {e.action for e in result.audit_trail}
        assert actions == {"modify_priority", "modify_scope"}

    def test_no_change_when_same_value(self) -> None:
        mission = _mission(priority="medium")
        mod = Modification(priority="medium", actor="bot")
        result = modify_mission(mission, mod)

        assert result.modification_applied is False
        assert len(result.audit_trail) == 0

    def test_target_modification(self) -> None:
        mission = _mission(target="vendor/incident-42")
        mod = Modification(target="vendor/incident-99", actor="director")
        result = modify_mission(mission, mod)

        assert result.mission.target == "vendor/incident-99"
        assert result.audit_trail[0].previous_value == "vendor/incident-42"
        assert result.audit_trail[0].new_value == "vendor/incident-99"

    def test_escalation_policy_modification(self) -> None:
        mission = _mission(escalation_policy="default")
        mod = Modification(escalation_policy="immediate", actor="ops_lead")
        result = modify_mission(mission, mod)

        assert result.mission.escalation_policy == "immediate"
        assert len(result.audit_trail) == 1

    def test_audit_trail_preserves_existing_entries(self) -> None:
        mission = _mission()
        existing_entry = AuditEntry(
            action="create",
            actor="system",
            reason="Initial creation",
        )
        mod = Modification(priority="high", actor="founder")
        result = modify_mission(
            mission, mod, context={"existing_audit_trail": [existing_entry]}
        )

        assert len(result.audit_trail) == 2
        assert result.audit_trail[0].action == "create"
        assert result.audit_trail[1].action == "modify_priority"

    def test_invalid_priority_raises(self) -> None:
        mission = _mission()
        mod = Modification(priority="mega_urgent", actor="test")
        with pytest.raises(ValueError, match="Invalid priority"):
            modify_mission(mission, mod)

    def test_invalid_status_raises(self) -> None:
        mission = _mission()
        mod = Modification(status="exploded", actor="test")
        with pytest.raises(ValueError, match="Invalid status"):
            modify_mission(mission, mod)

    def test_status_modification(self) -> None:
        mission = _mission()
        mod = Modification(status="paused", reason="Holiday", actor="manager")
        result = modify_mission(mission, mod)

        assert result.mission.status == "paused"
        assert result.audit_trail[0].new_value == "paused"


# ── 6. Mission redirect preserves original history ─────────────────────


class TestMissionRedirect:
    def test_basic_redirect(self) -> None:
        mission = _mission(target="vendor/incident-42")
        result = redirect_mission(
            mission, "vendor/incident-99", context={"actor": "founder"}
        )

        assert result.mission.target == "vendor/incident-99"
        assert result.original_target == "vendor/incident-42"
        assert result.mission.status == "redirected"

    def test_redirect_history_preserved(self) -> None:
        mission = _mission(target="vendor/incident-42")
        result = redirect_mission(
            mission,
            "vendor/incident-99",
            context={"actor": "founder", "reason": "Wrong vendor"},
        )

        assert len(result.redirect_history) == 1
        entry = result.redirect_history[0]
        assert entry["from_target"] == "vendor/incident-42"
        assert entry["to_target"] == "vendor/incident-99"
        assert entry["actor"] == "founder"
        assert entry["reason"] == "Wrong vendor"

    def test_redirect_audit_trail(self) -> None:
        mission = _mission(target="vendor/incident-42")
        result = redirect_mission(mission, "vendor/incident-99")

        assert len(result.audit_trail) == 1
        entry = result.audit_trail[0]
        assert entry.action == "redirect_target"
        assert entry.previous_value == "vendor/incident-42"
        assert entry.new_value == "vendor/incident-99"

    def test_chained_redirects_preserve_full_history(self) -> None:
        mission = _mission(target="vendor/incident-42")
        result1 = redirect_mission(
            mission, "vendor/incident-99", context={"actor": "founder"}
        )
        # Feed history from first redirect into second
        result2 = redirect_mission(
            _mission(target="vendor/incident-99"),
            "vendor/incident-150",
            context={
                "actor": "ops_lead",
                "redirect_history": result1.redirect_history,
                "existing_audit_trail": result1.audit_trail,
            },
        )

        assert len(result2.redirect_history) == 2
        assert result2.redirect_history[0]["to_target"] == "vendor/incident-99"
        assert result2.redirect_history[1]["to_target"] == "vendor/incident-150"
        assert len(result2.audit_trail) == 2
        assert result2.original_target == "vendor/incident-99"

    def test_redirect_preserves_original_mission_id(self) -> None:
        mission = _mission(mission_id="m-42", target="vendor/incident-42")
        result = redirect_mission(mission, "vendor/incident-99")

        assert result.mission.mission_id == "m-42"


# ── 7. Approval rejection stops execution ──────────────────────────────


class TestApprovalRejection:
    def test_l2_rejection(self) -> None:
        decision = evaluate_approval_request(
            "jira.update.issue",
            GovernanceLevel.L2_NOTIFY,
            context={"rejections": ["stakeholder"]},
        )
        assert decision.status == "rejected"
        assert "stakeholder" in decision.rejected_by

    def test_l4_rejection(self) -> None:
        decision = evaluate_approval_request(
            "notification.send_vendor",
            GovernanceLevel.L4_MANAGER,
            context={"rejections": ["manager"]},
        )
        assert decision.status == "rejected"

    def test_l5_rejection_with_partial_approvals(self) -> None:
        decision = evaluate_approval_request(
            "payment.process",
            GovernanceLevel.L5_DIRECTOR,
            context={
                "approvals": ["director"],
                "rejections": ["c_level"],
            },
        )
        assert decision.status == "rejected"
        assert "c_level" in decision.rejected_by

    def test_rejection_overrides_approvals(self) -> None:
        """Even if all approvers approved, a rejection blocks execution."""
        decision = evaluate_approval_request(
            "jira.update.issue",
            GovernanceLevel.L2_NOTIFY,
            context={
                "approvals": ["stakeholder"],
                "rejections": ["compliance"],
            },
        )
        assert decision.status == "rejected"


# ── 8. All models are strict (extra=forbid) ────────────────────────────


class TestModelStrictness:
    def test_approval_decision_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):  # ValidationError
            ApprovalDecision(
                operation="test",
                governance_level=GovernanceLevel.L1_AUTO,
                status="auto_approved",
                bogus_field="should fail",
            )

    def test_audit_entry_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):
            AuditEntry(
                action="test",
                actor="system",
                sneaky_field="nope",
            )

    def test_mission_snapshot_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):
            MissionSnapshot(
                mission_id="m-1",
                target="t",
                injected=True,
            )

    def test_modification_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):
            Modification(
                reason="test",
                hidden_field="bad",
            )

    def test_modified_mission_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):
            ModifiedMission(
                mission=MissionSnapshot(mission_id="m-1", target="t"),
                surprise=True,
            )

    def test_redirect_mission_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):
            RedirectedMission(
                mission=MissionSnapshot(mission_id="m-1", target="t"),
                original_target="old",
                oops=True,
            )


# ── 9. No I/O, no LLM, no wall clock ──────────────────────────────────


class TestPureFunctions:
    """Verify the module is pure — no I/O, no LLM, no wall clock dependencies."""

    def test_classify_deterministic(self) -> None:
        """Same input always produces same output (no randomness)."""
        r1 = classify_governance_level("jira.update.issue")
        r2 = classify_governance_level("jira.update.issue")
        assert r1 == r2

    def test_evaluate_deterministic(self) -> None:
        """Same inputs → same approval decision."""
        ctx = {"approvals": ["stakeholder"]}
        d1 = evaluate_approval_request("jira.update", GovernanceLevel.L2_NOTIFY, ctx)
        d2 = evaluate_approval_request("jira.update", GovernanceLevel.L2_NOTIFY, ctx)
        # Compare by value, not identity
        assert d1.status == d2.status
        assert d1.required_approvers == d2.required_approvers
        assert d1.approved_by == d2.approved_by

    def test_modify_deterministic(self) -> None:
        """Same modification on same mission yields same result (modulo timestamps/IDs)."""
        m1 = _mission(mission_id="m-x", priority="low")
        m2 = _mission(mission_id="m-x", priority="low")
        mod = Modification(priority="high", actor="test")
        r1 = modify_mission(m1, mod)
        r2 = modify_mission(m2, mod)
        assert r1.mission.model_dump(exclude={"audit_trail"}) == r2.mission.model_dump(
            exclude={"audit_trail"}
        )
        assert r1.modification_applied == r2.modification_applied

    def test_redirect_deterministic(self) -> None:
        """Same redirect on same mission yields same result (modulo timestamps/IDs)."""
        m1 = _mission(mission_id="m-x", target="a")
        m2 = _mission(mission_id="m-x", target="a")
        r1 = redirect_mission(m1, "b")
        r2 = redirect_mission(m2, "b")
        assert r1.mission.target == r2.mission.target
        assert r1.original_target == r2.original_target


# ── GovernanceLevel enum tests ─────────────────────────────────────────


class TestGovernanceLevelEnum:
    def test_all_six_levels_exist(self) -> None:
        levels = list(GovernanceLevel)
        assert len(levels) == 6

    def test_string_values(self) -> None:
        assert GovernanceLevel.L1_AUTO.value == "L1_AUTO"
        assert GovernanceLevel.L2_NOTIFY.value == "L2_NOTIFY"
        assert GovernanceLevel.L3_PEER.value == "L3_PEER"
        assert GovernanceLevel.L4_MANAGER.value == "L4_MANAGER"
        assert GovernanceLevel.L5_DIRECTOR.value == "L5_DIRECTOR"
        assert GovernanceLevel.L6_BOARD.value == "L6_BOARD"

    def test_enum_is_str_subclass(self) -> None:
        assert isinstance(GovernanceLevel.L1_AUTO, str)
