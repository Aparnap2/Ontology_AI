"""Tests for BA artifact base model + strategy artifacts + governance gate + strategy workflow."""
from __future__ import annotations

import pytest

from src.schemas.ba_artifact import BaseArtifact, ArtifactLifecycleStatus
from src.schemas.strategy_artifacts import (
    BusinessObjectives,
    ChangeStrategy,
    CurrentStateDescription,
    RiskAnalysisResults,
    SolutionEvaluationReport,
)
from src.governance_gate import GovernanceGate, GovernanceGateError
from src.ontology.action_types import PlannedAction
from src.schemas.engagement_state import EngagementState
from src.workflows.strategy_workflow import StrategyWorkflow


class TestArtifactLifecycleStatus:
    def test_has_required_states(self) -> None:
        assert ArtifactLifecycleStatus.PROPOSED.value == "proposed"
        assert ArtifactLifecycleStatus.ANALYZED.value == "analyzed"
        assert ArtifactLifecycleStatus.APPROVED.value == "approved"
        assert ArtifactLifecycleStatus.EVALUATED.value == "evaluated"
        assert ArtifactLifecycleStatus.ARCHIVED.value == "archived"


class TestBaseArtifact:
    def test_creates_with_required_id(self) -> None:
        a = BaseArtifact(artifact_id="test-1")
        assert a.artifact_id == "test-1"
        assert a.version == 1
        assert a.status == ArtifactLifecycleStatus.PROPOSED
        assert a.provenance == []
        assert a.producer == ""
        assert a.consumer_links == []

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValueError, match="extra"):
            BaseArtifact(artifact_id="test-2", unknown_field="x")  # type: ignore[call-arg]

    def test_provenance_is_traceable(self) -> None:
        a = BaseArtifact(artifact_id="test-3", provenance=["src:chat-001"])
        assert "src:chat-001" in a.provenance


class TestCurrentStateDescription:
    def test_from_truth_findings_creates_artifact(self) -> None:
        findings = [
            {"kind": "missing_owner", "summary": "Party abc has no owner", "target_id": "p-abc"},
            {"kind": "overdue_money_event", "summary": "Invoice x is overdue", "target_id": "m-x"},
            {"kind": "blocked_engagement", "summary": "Deal y is blocked", "target_id": "e-y"},
        ]
        cs = CurrentStateDescription.from_truth_findings(
            artifact_id="cs-1", truth_findings=findings, discovery_refs=["src:chat-001"],
        )
        assert cs.artifact_id == "cs-1"
        assert len(cs.missing_owners) == 1
        assert len(cs.overdue_items) == 1
        assert len(cs.known_bottlenecks) == 1
        assert cs.producer == "StrategyWorkflow"
        assert len(cs.provenance) == 3

    def test_empty_findings_produces_valid_state(self) -> None:
        cs = CurrentStateDescription.from_truth_findings("cs-2", [], [])
        assert cs.artifact_id == "cs-2"
        assert len(cs.weaknesses) == 0
        assert len(cs.known_bottlenecks) == 0

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValueError, match="extra"):
            CurrentStateDescription(
                artifact_id="cs-bad", summary="test", extra_field="x",  # type: ignore[call-arg]
            )


class TestBusinessObjectives:
    def test_from_operator_goal_and_current_state(self) -> None:
        cs = CurrentStateDescription(
            artifact_id="cs-1", summary="test",
            known_bottlenecks=["Engagement e-1 is blocked"],
        )
        bo = BusinessObjectives.from_operator_goal("bo-1", "Speed up deal flow", cs)
        assert bo.artifact_id == "bo-1"
        assert bo.goal_summary == "Speed up deal flow"
        assert "e-1" in bo.objectives[0]
        assert bo.linked_current_state_id == "cs-1"


class TestRiskAnalysisResults:
    def test_creates_with_risk_list(self) -> None:
        r = RiskAnalysisResults.from_gaps(
            artifact_id="ra-1",
            linked_current_state_id="cs-1",
            linked_objectives_id="bo-1",
            bottlenecks=["Deal y is blocked"],
            missing_owners=[],
            provenance=[],
        )
        assert len(r.risks) == 1
        assert r.risks[0]["risk_type"] == "bottleneck"
        assert r.risks[0]["severity"] == "high"
        assert r.linked_current_state_id == "cs-1"
        assert r.linked_objectives_id == "bo-1"

    def test_from_gaps_bottleneck_and_missing_owner(self) -> None:
        r = RiskAnalysisResults.from_gaps(
            artifact_id="ra-2",
            linked_current_state_id="cs-1",
            linked_objectives_id="bo-1",
            bottlenecks=["Deal y is blocked", "Server down"],
            missing_owners=["Party p-1", "Party p-2"],
            provenance=["src:cs-1"],
        )
        assert len(r.risks) == 4
        assert r.risks[0]["risk_type"] == "bottleneck"
        assert r.risks[2]["risk_type"] == "missing_owner"
        assert r.risks[2]["severity"] == "medium"
        assert r.producer == "StrategyWorkflow"


class TestChangeStrategy:
    def test_creates_with_fields(self) -> None:
        s = ChangeStrategy(
            artifact_id="csg-1",
            approach="Agile pilot",
            solution_scope="eng-1",
            key_milestones=["Approve", "Deploy", "Evaluate"],
            linked_risk_id="ra-1",
            linked_objectives_id="bo-1",
            linked_current_state_id="cs-1",
        )
        assert s.artifact_id == "csg-1"
        assert len(s.key_milestones) == 3


class TestSolutionEvaluationReport:
    def test_creates_with_fields(self) -> None:
        e = SolutionEvaluationReport(
            artifact_id="eval-1",
            expected_outcome="Resolve bottleneck",
            actual_outcome="Bottleneck partially resolved",
            metrics={"resolution_time_hours": 48},
            limitations=["Limited data"],
            recommended_actions=["Escalate"],
            linked_strategy_id="csg-1",
            linked_workflow_id="wf-1",
        )
        assert e.artifact_id == "eval-1"
        assert e.expected_outcome == "Resolve bottleneck"
        assert e.metrics["resolution_time_hours"] == 48

    def test_from_outcome_creates_report(self) -> None:
        report = SolutionEvaluationReport.from_outcome(
            artifact_id="eval-out-1",
            expected_outcome="Reduce bottlenecks",
            actual_outcome="50% reduction achieved",
            metrics={"reduction_pct": 50},
            limitations=["Sample size small"],
            recommended_actions=["Expand pilot"],
            linked_strategy_id="csg-1",
            linked_workflow_id="wf-1",
            provenance=["src:chat-001"],
        )
        assert report.artifact_id == "eval-out-1"
        assert report.expected_outcome == "Reduce bottlenecks"
        assert report.actual_outcome == "50% reduction achieved"
        assert report.metrics["reduction_pct"] == 50
        assert report.producer == "StrategyWorkflow"

    def test_from_outcome_links_to_strategy_and_workflow(self) -> None:
        report = SolutionEvaluationReport.from_outcome(
            artifact_id="eval-out-2",
            expected_outcome="Test",
            actual_outcome="Done",
            metrics={},
            limitations=[],
            recommended_actions=[],
            linked_strategy_id="csg-99",
            linked_workflow_id="wf-42",
            provenance=[],
        )
        assert report.linked_strategy_id == "csg-99"
        assert report.linked_workflow_id == "wf-42"

    def test_preserves_provenance_chain(self) -> None:
        report = SolutionEvaluationReport.from_outcome(
            artifact_id="eval-out-3",
            expected_outcome="Test",
            actual_outcome="Done",
            metrics={},
            limitations=[],
            recommended_actions=[],
            linked_strategy_id="csg-1",
            linked_workflow_id="wf-1",
            provenance=["src:chat-001", "analysis:v1"],
        )
        assert "src:chat-001" in report.provenance
        assert "analysis:v1" in report.provenance


class TestBaseArtifactVersioning:
    def test_new_version_increments_version(self) -> None:
        a = BaseArtifact(artifact_id="test-v1")
        v2 = a.new_version()
        assert v2.version == 2

    def test_new_version_resets_status_to_proposed(self) -> None:
        a = BaseArtifact(
            artifact_id="test-v1",
            status=ArtifactLifecycleStatus.APPROVED,
        )
        v2 = a.new_version()
        assert v2.status == ArtifactLifecycleStatus.PROPOSED

    def test_new_version_preserves_artifact_id(self) -> None:
        a = BaseArtifact(artifact_id="test-v1")
        v2 = a.new_version()
        assert v2.artifact_id == "test-v1"

    def test_new_version_carries_provenance_forward(self) -> None:
        a = BaseArtifact(
            artifact_id="test-v1",
            provenance=["src:chat-001"],
        )
        v2 = a.new_version()
        assert "src:chat-001" in v2.provenance
        assert any("v1->v2" in p for p in v2.provenance)

    def test_original_is_unchanged_after_new_version(self) -> None:
        a = BaseArtifact(artifact_id="test-v1", version=1)
        _ = a.new_version()
        assert a.version == 1
        assert a.artifact_id == "test-v1"

    def test_is_finalized_false_when_proposed(self) -> None:
        a = BaseArtifact(artifact_id="test-v1")
        assert a.is_finalized is False

    def test_is_finalized_true_when_approved(self) -> None:
        a = BaseArtifact(
            artifact_id="test-v1",
            status=ArtifactLifecycleStatus.APPROVED,
        )
        assert a.is_finalized is True

    def test_is_finalized_true_when_implemented(self) -> None:
        a = BaseArtifact(
            artifact_id="test-v1",
            status=ArtifactLifecycleStatus.IMPLEMENTED,
        )
        assert a.is_finalized is True

    def test_artifact_is_immutable_after_creation(self) -> None:
        a = BaseArtifact(artifact_id="test-v1")
        with pytest.raises(ValueError, match="frozen"):
            a.status = ArtifactLifecycleStatus.APPROVED  # type: ignore[misc]


class TestChangeStrategyFromAnalysis:
    def test_from_analysis_creates_strategy(self) -> None:
        s = ChangeStrategy.from_analysis(
            artifact_id="csg-ana-1",
            approach="Incremental rollout",
            solution_scope="eng-1 scope",
            key_milestones=["Approve", "Deploy", "Evaluate"],
            linked_risk_id="ra-1",
            linked_objectives_id="bo-1",
            linked_current_state_id="cs-1",
            provenance=["src:cs-1", "src:bo-1"],
        )
        assert s.artifact_id == "csg-ana-1"
        assert s.approach == "Incremental rollout"
        assert len(s.key_milestones) == 3
        assert s.linked_risk_id == "ra-1"
        assert s.linked_objectives_id == "bo-1"
        assert s.linked_current_state_id == "cs-1"
        assert "src:cs-1" in s.provenance
        assert s.producer == "StrategyWorkflow"


class TestGovernanceGateEnhanced:
    def test_blocks_high_blast_radius_when_max_is_medium(self) -> None:
        action = PlannedAction(
            id="pa-test", type="test", title="test",
            blast_radius="high", status="draft",
            requested_by="test",
            target_object_type="Workflow", target_id="wf-test",
            rationale="test", requires_approval=True,
        )
        with pytest.raises(GovernanceGateError, match="blast radius"):
            GovernanceGate.check_blast_radius(action, max_allowed="medium")

    def test_allows_low_blast_radius_when_max_is_medium(self) -> None:
        action = PlannedAction(
            id="pa-test", type="test", title="test",
            blast_radius="low", status="draft",
            requested_by="test",
            target_object_type="Workflow", target_id="wf-test",
            rationale="test", requires_approval=True,
        )
        GovernanceGate.check_blast_radius(action, max_allowed="medium")

    def test_blocks_unauthorized_actor(self) -> None:
        action = PlannedAction(
            id="pa-test", type="test", title="test",
            blast_radius="low", status="approved",
            requested_by="alice",
            target_object_type="Workflow", target_id="wf-test",
            rationale="test", requires_approval=True,
        )
        authorized = {"bob", "charlie"}
        with pytest.raises(GovernanceGateError, match="not authorized"):
            GovernanceGate.check_actor_authorized("alice", action, authorized)

    def test_allows_authorized_actor(self) -> None:
        action = PlannedAction(
            id="pa-test", type="test", title="test",
            blast_radius="low", status="approved",
            requested_by="bob",
            target_object_type="Workflow", target_id="wf-test",
            rationale="test", requires_approval=True,
        )
        authorized = {"bob", "charlie"}
        GovernanceGate.check_actor_authorized("bob", action, authorized)

    def test_is_execution_allowed_checks_all_gates(self) -> None:
        csg = ChangeStrategy(
            artifact_id="csg-test", approach="test",
            solution_scope="test", status=ArtifactLifecycleStatus.APPROVED,
        )
        action = PlannedAction(
            id="pa-test", type="test", title="test",
            blast_radius="low", status="approved",
            requested_by="bob",
            target_object_type="Workflow", target_id="wf-test",
            rationale="test", requires_approval=True,
        )
        assert GovernanceGate.is_execution_allowed(
            csg, action,
            actor="bob",
            max_blast_radius="medium",
            authorized_actors={"bob"},
        ) is True

    def test_is_execution_allowed_blocks_when_actor_unauthorized(self) -> None:
        csg = ChangeStrategy(
            artifact_id="csg-test", approach="test",
            solution_scope="test", status=ArtifactLifecycleStatus.APPROVED,
        )
        action = PlannedAction(
            id="pa-test", type="test", title="test",
            blast_radius="low", status="approved",
            requested_by="alice",
            target_object_type="Workflow", target_id="wf-test",
            rationale="test", requires_approval=True,
        )
        assert GovernanceGate.is_execution_allowed(
            csg, action,
            actor="alice",
            max_blast_radius="medium",
            authorized_actors={"bob"},
        ) is False

    def test_is_execution_allowed_blocks_when_blast_too_high(self) -> None:
        csg = ChangeStrategy(
            artifact_id="csg-test", approach="test",
            solution_scope="test", status=ArtifactLifecycleStatus.APPROVED,
        )
        action = PlannedAction(
            id="pa-test", type="test", title="test",
            blast_radius="high", status="approved",
            requested_by="bob",
            target_object_type="Workflow", target_id="wf-test",
            rationale="test", requires_approval=True,
        )
        assert GovernanceGate.is_execution_allowed(
            csg, action,
            actor="bob",
            max_blast_radius="medium",
            authorized_actors={"bob"},
        ) is False


class TestMergePatchFinalizedArtifactProtection:
    def test_rejects_patch_on_finalized_artifact(self) -> None:
        state = EngagementState(
            engagement_id="e1", tenant_id="t1",
            workspace_mode="workspace",
            phase="governance_review",
            current_state_descriptions=[
                {"artifact_id": "cs-1", "status": "approved",
                 "summary": "Done", "version": 1},
            ],
        )
        patch = {
            "current_state_descriptions": [
                {"artifact_id": "cs-2", "summary": "New"},
            ],
        }
        with pytest.raises(ValueError, match="finalized"):
            state.merge_patch(patch)

    def test_allows_patch_on_unfinalized_artifact(self) -> None:
        state = EngagementState(
            engagement_id="e1", tenant_id="t1",
            workspace_mode="workspace",
            phase="discovery",
            current_state_descriptions=[
                {"artifact_id": "cs-1", "status": "proposed",
                 "summary": "WIP", "version": 1},
            ],
        )
        patch = {
            "current_state_descriptions": [
                {"artifact_id": "cs-2", "summary": "New"},
            ],
        }
        new_state = state.merge_patch(patch)
        assert len(new_state.current_state_descriptions) == 2

    def test_rejects_patch_on_implemented_artifact(self) -> None:
        state = EngagementState(
            engagement_id="e1", tenant_id="t1",
            workspace_mode="workspace",
            phase="governance_review",
            risk_analyses=[
                {"artifact_id": "ra-1", "status": "implemented",
                 "summary": "Done", "version": 1},
            ],
        )
        patch = {
            "risk_analyses": [
                {"artifact_id": "ra-2", "risks": []},
            ],
        }
        with pytest.raises(ValueError, match="finalized"):
            state.merge_patch(patch)

    def test_add_artifact_version_replaces_finalized_artifact(self) -> None:
        state = EngagementState(
            engagement_id="e1", tenant_id="t1",
            workspace_mode="workspace",
            phase="governance_review",
            current_state_descriptions=[
                {"artifact_id": "cs-1", "status": "approved",
                 "summary": "Old", "version": 1},
            ],
        )
        new_version = {
            "artifact_id": "cs-1", "status": "proposed",
            "summary": "New v2", "version": 2,
        }
        updated = state.add_artifact_version(
            "current_state_descriptions", new_version,
        )
        assert len(updated.current_state_descriptions) == 1
        assert updated.current_state_descriptions[0]["version"] == 2
        assert updated.current_state_descriptions[0]["summary"] == "New v2"
        assert updated.current_state_descriptions[0]["status"] == "proposed"


class TestStrategyWorkflowEvaluation:
    def test_run_with_planned_outcomes_adds_evaluation(self) -> None:
        wf = StrategyWorkflow()
        findings = [
            {"kind": "missing_owner", "summary": "Party p-1 no owner",
             "target_id": "p-1"},
        ]
        resp = wf.run(
            tenant_id="t1", engagement_id="e1",
            truth_findings=findings,
            operator_goal="Fix bottlenecks",
            discover_refs=["src:chat-001"],
            planned_outcomes={
                "expected_outcome": "Reduce bottlenecks",
                "actual_outcome": "50% reduction",
                "metrics": {"pct": 50},
                "limitations": [],
                "recommended_actions": ["Scale"],
                "linked_strategy_id": "csg-1",
                "linked_workflow_id": "wf-1",
            },
        )
        patch = resp.engagement_state_patch or {}
        assert "solution_evaluations" in patch
        assert len(patch["solution_evaluations"]) == 1
        assert patch["solution_evaluations"][0]["expected_outcome"] == "Reduce bottlenecks"

    def test_run_without_planned_outcomes_no_evaluation(self) -> None:
        wf = StrategyWorkflow()
        resp = wf.run("t1", "e1", [])
        patch = resp.engagement_state_patch or {}
        assert "solution_evaluations" not in patch


class TestGovernanceGate:
    def test_blocks_unapproved_strategy(self) -> None:
        csg = ChangeStrategy(
            artifact_id="csg-test",
            approach="test",
            solution_scope="test",
        )
        with pytest.raises(GovernanceGateError, match="approved"):
            GovernanceGate.check_strategy(csg)

    def test_allows_approved_strategy(self) -> None:
        csg = ChangeStrategy(
            artifact_id="csg-test",
            approach="test",
            solution_scope="test",
            status=ArtifactLifecycleStatus.APPROVED,
        )
        GovernanceGate.check_strategy(csg)

    def test_blocks_unapproved_planned_action(self) -> None:
        action = PlannedAction(
            id="pa-test", type="test", title="test",
            blast_radius="low", status="draft",
            requested_by="test",
            target_object_type="Workflow", target_id="wf-test",
            rationale="test", requires_approval=True,
        )
        with pytest.raises(GovernanceGateError, match="approved"):
            GovernanceGate.check_planned_action(action)

    def test_allows_approved_planned_action(self) -> None:
        action = PlannedAction(
            id="pa-test", type="test", title="test",
            blast_radius="low", status="approved",
            requested_by="test",
            target_object_type="Workflow", target_id="wf-test",
            rationale="test", requires_approval=True,
        )
        GovernanceGate.check_planned_action(action)

    def test_is_execution_allowed_both_approved(self) -> None:
        csg = ChangeStrategy(
            artifact_id="csg-test", approach="test",
            solution_scope="test", status=ArtifactLifecycleStatus.APPROVED,
        )
        action = PlannedAction(
            id="pa-test", type="test", title="test",
            blast_radius="low", status="approved",
            requested_by="test",
            target_object_type="Workflow", target_id="wf-test",
            rationale="test", requires_approval=True,
        )
        assert GovernanceGate.is_execution_allowed(csg, action) is True

    def test_is_execution_allowed_blocked_when_strategy_not_approved(self) -> None:
        csg = ChangeStrategy(
            artifact_id="csg-test", approach="test", solution_scope="test",
        )
        action = PlannedAction(
            id="pa-test", type="test", title="test",
            blast_radius="low", status="approved",
            requested_by="test",
            target_object_type="Workflow", target_id="wf-test",
            rationale="test", requires_approval=True,
        )
        assert GovernanceGate.is_execution_allowed(csg, action) is False


class TestStrategyWorkflow:
    def test_run_produces_four_artifacts(self) -> None:
        wf = StrategyWorkflow()
        findings = [
            {"kind": "missing_owner", "summary": "Party p-1 no owner", "target_id": "p-1"},
            {"kind": "overdue_money_event", "summary": "Invoice i-1 overdue", "target_id": "i-1"},
        ]
        resp = wf.run(
            tenant_id="t1", engagement_id="e1",
            truth_findings=findings,
            operator_goal="Fix bottlenecks",
            discover_refs=["src:chat-001"],
        )
        patch = resp.engagement_state_patch or {}
        assert "current_state_descriptions" in patch
        assert "business_objectives" in patch
        assert "risk_analyses" in patch
        assert "change_strategies" in patch

    def test_specialist_response_shape(self) -> None:
        """StrategyWorkflow returns Strategy specialist identity (V6)."""
        wf = StrategyWorkflow()
        resp = wf.run("t1", "e1", [])
        assert resp.specialist == "Strategy"
        assert resp.workflow_name == "StrategyWorkflow"
        assert resp.requires_hitl is True
