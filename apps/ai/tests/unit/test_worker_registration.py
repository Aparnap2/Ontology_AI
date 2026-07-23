"""Tests for worker.py / workflows.__init__ V5.1 workflow registration.

Asserts the V5.1 default contract: exactly 6 canonical workflows.
V6 StrategyWorkflow is gated behind ``ENABLE_V6_WORKFLOWS=on``.
"""
from __future__ import annotations

import os

import pytest


class TestWorkerRegistration:
    """Verify the V5.1 active workflow roster contract."""

    # V5.1 canonical roster: exactly 6 (PRD §7).
    CANONICAL_V51 = {
        "ChiefOfStaffWorkflow",
        "DiscoveryWorkflow",
        "OntologyMappingWorkflow",
        "TruthAnalysisWorkflow",
        "WorkflowBuilderWorkflow",
        "GovernanceWorkflow",
    }

    V6_WORKFLOWS = {"StrategyWorkflow"}

    ALL_V51_PLUS_V6 = CANONICAL_V51 | V6_WORKFLOWS

    def test_default_roster_is_exactly_6(self):
        """Default ACTIVE_WORKFLOWS (no flags) has exactly 6 entries."""
        from src.workflows import ACTIVE_WORKFLOWS

        assert len(ACTIVE_WORKFLOWS) == 6, (
            f"V5.1 contract requires exactly 6 active workflows, got {len(ACTIVE_WORKFLOWS)}: "
            f"{sorted(ACTIVE_WORKFLOWS.keys())}"
        )
        assert set(ACTIVE_WORKFLOWS.keys()) == self.CANONICAL_V51, (
            f"V5.1 roster mismatch. Expected: {sorted(self.CANONICAL_V51)}, "
            f"Got: {sorted(ACTIVE_WORKFLOWS.keys())}"
        )

    def test_default_roster_excludes_v6(self):
        """StrategyWorkflow is NOT in the default ACTIVE_WORKFLOWS."""
        from src.workflows import ACTIVE_WORKFLOWS

        assert "StrategyWorkflow" not in ACTIVE_WORKFLOWS, (
            "StrategyWorkflow (V6) must not be in default ACTIVE_WORKFLOWS"
        )

    @pytest.mark.parametrize("flag_value", ["on"])
    def test_enable_v6_includes_strategy(self, flag_value, monkeypatch):
        """Setting ENABLE_V6_WORKFLOWS=on includes StrategyWorkflow.

        Only 'on' is accepted as truthy (exact match per PRD gating convention).
        Uses ``_build_active_workflows()`` / ``_build_route_map()`` directly
        instead of ``importlib.reload`` to avoid permanently mutating the
        shared ``sys.modules['src.workflows']`` state, which would cause
        downstream tests (e.g. ``test_default_route_map_excludes_strategy``)
        to see stale cached values.
        """
        monkeypatch.setenv("ENABLE_V6_WORKFLOWS", flag_value)

        # Test the build functions directly — no module reload needed.
        from src.workflows import _build_active_workflows, _build_route_map

        active = _build_active_workflows()
        assert "StrategyWorkflow" in active
        assert len(active) == 7

        route_map = _build_route_map()
        assert "@strategy" in route_map

    def test_default_route_map_excludes_strategy(self):
        """Default ROUTE_MAP does NOT include @strategy."""
        from src.workflows import ROUTE_MAP

        assert "@strategy" not in ROUTE_MAP, (
            "@strategy must not be in default ROUTE_MAP (V6 gated)"
        )

    def test_v51_workflows_importable(self):
        """All 6 V5.1 canonical workflows can be imported from their modules."""
        from src.workflows.discovery_workflow import DiscoveryWorkflow
        from src.workflows.ontology_mapping_workflow import (
            OntologyMappingWorkflow,
        )
        from src.workflows.truth_analysis_workflow import TruthAnalysisWorkflow
        from src.workflows.workflow_builder_workflow import WorkflowBuilderWorkflow
        from src.workflows.governance_workflow import GovernanceWorkflow
        from src.workflows.chief_of_staff_workflow import ChiefOfStaffWorkflow

        assert DiscoveryWorkflow is not None
        assert OntologyMappingWorkflow is not None
        assert TruthAnalysisWorkflow is not None
        assert WorkflowBuilderWorkflow is not None
        assert GovernanceWorkflow is not None
        assert ChiefOfStaffWorkflow is not None

    def test_v51_workflows_have_run_method(self):
        """Every V5.1 canonical workflow has a ``run()`` method."""
        from src.workflows import ACTIVE_WORKFLOWS

        for name, wf_cls in ACTIVE_WORKFLOWS.items():
            assert hasattr(wf_cls, "run"), f"{name} is missing run()"
            assert callable(wf_cls.run), f"{name}.run() is not callable"

    def test_worker_py_default_roster_ast(self):
        """Verify worker.py's _build_workflow_list has exactly 6 V5.1 defaults."""
        import ast

        worker_path = "src/worker.py"
        with open(worker_path) as f:
            tree = ast.parse(f.read())

        # Find the workflows list in _build_workflow_list
        workflows_list_elts: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_build_workflow_list":
                for sub in ast.walk(node):
                    if isinstance(sub, ast.List):
                        for elt in sub.elts:
                            if isinstance(elt, ast.Name):
                                workflows_list_elts.add(elt.id)

        assert "ChiefOfStaffWorkflow" in workflows_list_elts
        assert "DiscoveryWorkflow" in workflows_list_elts
        assert "OntologyMappingWorkflow" in workflows_list_elts
        assert "TruthAnalysisWorkflow" in workflows_list_elts
        assert "WorkflowBuilderWorkflow" in workflows_list_elts
        assert "GovernanceWorkflow" in workflows_list_elts
        # StrategyWorkflow should NOT be in the default list
        assert "StrategyWorkflow" not in workflows_list_elts, (
            "StrategyWorkflow must NOT be in default worker workflow list"
        )
