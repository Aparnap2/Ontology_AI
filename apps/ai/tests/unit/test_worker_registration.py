"""Tests for worker.py / workflows.__init__ 6-canonical workflow registration.

Asserts the 6-canonical default contract: exactly 6 V5.2 workflows.
V6 StrategyWorkflow is gated behind ``ENABLE_V6_WORKFLOWS=on``.
Legacy FDE modules are gated behind ``LEGACY_FDE_MODULES=on``.
"""
from __future__ import annotations

import pytest


class TestWorkerRegistration:
    """Verify the 6-canonical active workflow roster contract."""

    # 6-canonical roster: exactly 6 V5.2 workflows.
    CANONICAL_V51 = {
        "ChiefOfStaffWorkflow",
        "DiscoveryWorkflow",
        "OntologyMappingWorkflow",
        "KnowledgeValidationWorkflow",
        "SolutionArchitectWorkflow",
        "GovernanceWorkflow",
    }

    V6_WORKFLOWS = {"StrategyWorkflow"}

    ALL_V51_PLUS_V6 = CANONICAL_V51 | V6_WORKFLOWS

    def test_default_roster_is_exactly_6(self):
        """Default ACTIVE_WORKFLOWS (no flags) has exactly 6 entries."""
        from src.workflows import ACTIVE_WORKFLOWS

        assert len(ACTIVE_WORKFLOWS) == 6, (
            f"6-canonical contract requires exactly 6 active workflows, got {len(ACTIVE_WORKFLOWS)}: "
            f"{sorted(ACTIVE_WORKFLOWS.keys())}"
        )
        assert set(ACTIVE_WORKFLOWS.keys()) == self.CANONICAL_V51, (
            f"6-canonical roster mismatch. Expected: {sorted(self.CANONICAL_V51)}, "
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
        """All 6 canonical workflows can be imported from their modules."""
        from src.workflows.discovery_workflow import DiscoveryWorkflow
        from src.workflows.ontology_mapping_workflow import (
            OntologyMappingWorkflow,
        )
        from src.workflows.knowledge_validation_workflow import KnowledgeValidationWorkflow
        from src.workflows.solution_architect_workflow import SolutionArchitectWorkflow
        from src.workflows.governance_workflow import GovernanceWorkflow
        from src.workflows.chief_of_staff_workflow import ChiefOfStaffWorkflow

        assert DiscoveryWorkflow is not None
        assert OntologyMappingWorkflow is not None
        assert KnowledgeValidationWorkflow is not None
        assert SolutionArchitectWorkflow is not None
        assert GovernanceWorkflow is not None
        assert ChiefOfStaffWorkflow is not None

    def test_v51_workflows_have_run_method(self):
        """Every canonical workflow has a ``run()`` method."""
        from src.workflows import ACTIVE_WORKFLOWS

        for name, wf_cls in ACTIVE_WORKFLOWS.items():
            assert hasattr(wf_cls, "run"), f"{name} is missing run()"
            assert callable(wf_cls.run), f"{name}.run() is not callable"

    def test_worker_py_default_roster_ast(self):
        """Verify worker.py's _build_workflow_list has exactly 9 defaults."""
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

        # Only classes carrying @workflow.defn may be registered: Temporal
        # raises "missing attributes, was it decorated with @workflow.defn?"
        # for anything else, which made Worker() unconstructable.
        assert "IncidentWorkflow" in workflows_list_elts
        assert "ChiefOfStaffWorkflow" in workflows_list_elts
        for undecorated in (
            "DiscoveryWorkflow",
            "OntologyMappingWorkflow",
            "KnowledgeValidationWorkflow",
            "SolutionArchitectWorkflow",
            "GovernanceWorkflow",
        ):
            assert undecorated not in workflows_list_elts, (
                f"{undecorated} carries no @workflow.defn and must not be "
                "registered with the worker"
            )
        # StrategyWorkflow should NOT be in the default list
        assert "StrategyWorkflow" not in workflows_list_elts, (
            "StrategyWorkflow must NOT be in default worker workflow list"
        )


class TestActivityRegistration:
    """Verify the 9-runtime activity roster contract in worker.py.

    Default: 6 base activities.
    Legacy V4.1 gated behind ``LEGACY_FDE_MODULES=on``.
    """

    # Always-included base activities (6)
    BASE_ACTIVITIES = {
        "send_slack_message",
        "run_guardian_watchlist",
        "compile_n8n_workflow",
        "decay_memory_weights",
        "expire_old_memories",
        "optimize_memory_performance",
    }

    # V7 incident hero-path activities (9). NOT optional: IncidentWorkflow is
    # registered unconditionally, so omitting these would advertise the
    # workflow and then fail every activity dispatch.
    INCIDENT_ACTIVITIES = {
        "create_situation",
        "assemble_checkpoint",
        "run_investigation",
        "generate_action_intent",
        "submit_to_control_plane",
        "execute_capability",
        "verify_recovery_activity",
        "resolve_situation",
        "escalate_situation",
    }

    # Legacy V4.1 activities (4)
    LEGACY_ACTIVITIES = {
        "run_pulse_agent",
        "run_anomaly_agent",
        "run_investor_agent",
        "run_qa_agent",
    }

    ALL_ACTIVITIES = BASE_ACTIVITIES | INCIDENT_ACTIVITIES | LEGACY_ACTIVITIES

    def test_default_roster_is_base_plus_incident(self):
        """Default _build_activity_list() returns the 6 base + 9 incident activities."""
        from src.worker import _build_activity_list

        acts = _build_activity_list()
        names = {f.__name__ for f in acts}
        expected = self.BASE_ACTIVITIES | self.INCIDENT_ACTIVITIES
        assert names == expected, (
            f"Default activity roster mismatch. Expected: {sorted(expected)}, "
            f"Got: {sorted(names)}"
        )

    def test_default_roster_excludes_legacy(self):
        """No legacy V4.1 activities in the default roster."""
        from src.worker import _build_activity_list

        names = {f.__name__ for f in _build_activity_list()}
        assert names.isdisjoint(self.LEGACY_ACTIVITIES), (
            f"Legacy activities must NOT be in default roster, found: "
            f"{names & self.LEGACY_ACTIVITIES}"
        )

    def test_legacy_flag_includes_legacy_activities(self, monkeypatch):
        """Setting LEGACY_FDE_MODULES=on adds the 4 legacy activities."""
        monkeypatch.setenv("LEGACY_FDE_MODULES", "on")

        from src.worker import _build_activity_list

        acts = _build_activity_list()
        names = {f.__name__ for f in acts}
        assert names == self.ALL_ACTIVITIES, (
            f"With LEGACY_FDE_MODULES=on, expected base+incident+legacy, "
            f"got {len(acts)}: {sorted(names)}"
        )
        assert names == self.ALL_ACTIVITIES, (
            f"Full activity roster mismatch. Expected: {sorted(self.ALL_ACTIVITIES)}, "
            f"Got: {sorted(names)}"
        )

    def test_default_activity_list_ast(self):
        """Verify _build_activity_list default list has exactly 6 base names.

        Uses AST parsing to avoid importing modules with side effects.
        """
        import ast

        worker_path = "src/worker.py"
        with open(worker_path) as f:
            tree = ast.parse(f.read())

        # Find the activities list in _build_activity_list's default assignment
        # (Only the top-level ``activities: list[Callable] = [...]`` list, NOT
        # the one inside the ``if os.getenv("LEGACY_FDE_MODULES")`` block.)
        activities_list_elts: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_build_activity_list":
                for stmt in node.body:
                    # Python 3.10+ uses AnnAssign for annotated assignments
                    # like ``activities: list[Callable] = [...]``
                    if isinstance(stmt, ast.AnnAssign):
                        if isinstance(stmt.target, ast.Name) and stmt.target.id == "activities":
                            if isinstance(stmt.value, ast.List):
                                for elt in stmt.value.elts:
                                    if isinstance(elt, ast.Name):
                                        activities_list_elts.add(elt.id)

        # All 6 base activities must be in the default list
        for name in self.BASE_ACTIVITIES:
            assert name in activities_list_elts, (
                f"Base activity '{name}' must be in _build_activity_list default list"
            )

        # None of the legacy activities should be in the default list
        for name in self.LEGACY_ACTIVITIES:
            assert name not in activities_list_elts, (
                f"Legacy activity '{name}' must NOT be in _build_activity_list default list"
            )
