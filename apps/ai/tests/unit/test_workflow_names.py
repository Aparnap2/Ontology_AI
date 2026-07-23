"""Tests for OntologyAI V5.1 workflow roster (PRD §7).

Default roster is exactly 6 V5.1 canonical workflows.
V6 StrategyWorkflow is gated behind ``ENABLE_V6_WORKFLOWS=on``.
Run:
    cd /home/aparna/Desktop/iterate_swarm/apps/ai
    uv run pytest tests/unit/test_workflow_names.py -v
"""
import os
import pytest

from src.workflows import ACTIVE_WORKFLOWS, WORKFLOW_REGISTRY


CANONICAL_V5_WORKFLOWS = {
    "ChiefOfStaffWorkflow",
    "DiscoveryWorkflow",
    "OntologyMappingWorkflow",
    "TruthAnalysisWorkflow",
    "WorkflowBuilderWorkflow",
    "GovernanceWorkflow",
}


class TestWorkflowRoster:
    def test_default_roster_is_exactly_6(self):
        assert len(ACTIVE_WORKFLOWS) == 6

    def test_exact_names_match_prd(self):
        assert set(ACTIVE_WORKFLOWS.keys()) == CANONICAL_V5_WORKFLOWS

    def test_default_roster_excludes_v6(self):
        assert "StrategyWorkflow" not in ACTIVE_WORKFLOWS

    def test_registry_matches_active(self):
        for name in ACTIVE_WORKFLOWS:
            assert name in WORKFLOW_REGISTRY
            assert WORKFLOW_REGISTRY[name] is not None

    def test_no_legacy_in_active_roster(self):
        legacy = {
            "PulseWorkflow", "InvestorWorkflow", "FPAWorkflow",
            "GrowthAnalyticsWorkflow", "ReliabilityWorkflow", "CommsWorkflow",
            "QAWorkflow", "FinanceWorkflow", "DataWorkflow", "OpsWorkflow",
            "SelfAnalysisWorkflow", "EvalLoopWorkflow", "CompressionWorkflow",
            "WeightDecayWorkflow", "MemoryMaintenanceWorkflow",
        }
        assert not (set(ACTIVE_WORKFLOWS.keys()) & legacy)

    def test_each_workflow_has_run_method(self):
        for name, wf_cls in ACTIVE_WORKFLOWS.items():
            assert hasattr(wf_cls, "run"), f"{name} missing run()"

    # ── V6 gated path ──────────────────────────────────────────────────────

    def test_strategy_importable_but_not_default(self):
        """StrategyWorkflow is always importable but not in default roster."""
        from src.workflows.strategy_workflow import StrategyWorkflow as SW
        assert SW is not None
        assert "StrategyWorkflow" not in ACTIVE_WORKFLOWS

    # ── Specialist identity tests (PRD §7) ─────────────────────────────────

    def test_strategy_workflow_specialist_is_strategy(self):
        """StrategyWorkflow.run() must return specialist='Strategy', not 'ChiefOfStaff'."""
        from src.workflows.strategy_workflow import StrategyWorkflow
        wf = StrategyWorkflow()
        response = wf.run(
            tenant_id="test-tenant",
            engagement_id="test-engagement",
            truth_findings=[{"finding": "test"}],
        )
        assert response.specialist == "Strategy", (
            f"Expected specialist='Strategy', got {response.specialist!r}"
        )

    def test_strategy_workflow_workflow_name(self):
        """StrategyWorkflow.run() must return workflow_name='StrategyWorkflow'."""
        from src.workflows.strategy_workflow import StrategyWorkflow
        wf = StrategyWorkflow()
        response = wf.run(
            tenant_id="test-tenant",
            engagement_id="test-engagement",
            truth_findings=[{"finding": "test"}],
        )
        assert response.workflow_name == "StrategyWorkflow"
