"""Tests for OntologyAI V5.1 workflow roster (PRD §7).

Asserts exactly 6 active workflows are registered and their names match PRD §7.
Run:
    cd /home/aparna/Desktop/iterate_swarm/apps/ai
    uv run pytest tests/unit/test_workflow_names.py -v
"""
import pytest

from src.workflows import ACTIVE_WORKFLOWS, WORKFLOW_REGISTRY


EXPECTED_WORKFLOWS = {
    "ChiefOfStaffWorkflow",
    "DiscoveryWorkflow",
    "OntologyMappingWorkflow",
    "TruthAnalysisWorkflow",
    "WorkflowBuilderWorkflow",
    "GovernanceWorkflow",
    "StrategyWorkflow",
}


class TestWorkflowRoster:
    def test_exactly_seven_active_workflows(self):
        assert len(ACTIVE_WORKFLOWS) == 7

    def test_exact_names_match_prd(self):
        assert set(ACTIVE_WORKFLOWS.keys()) == EXPECTED_WORKFLOWS

    def test_registry_has_all_seven(self):
        for name in EXPECTED_WORKFLOWS:
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
