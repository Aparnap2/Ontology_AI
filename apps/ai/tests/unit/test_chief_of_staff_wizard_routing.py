"""Tests for OntologyAI V5.1 — ChiefOfStaff wizard intent routing (PRD §25.2).

Tests verify that the ontology setup wizard intents are correctly:
1. Classified by ``classify_intent()``
2. Routed to the correct specialist workflows via ``route()``
3. Do NOT break existing intent classification or routing

Run:
    cd /home/aparna/Desktop/iterate_swarm/apps/ai
    uv run pytest tests/unit/test_chief_of_staff_wizard_routing.py -v
"""
import pytest

from src.workflows.chief_of_staff_workflow import ChiefOfStaffCore


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def core() -> ChiefOfStaffCore:
    return ChiefOfStaffCore()


# =============================================================================
# Wizard Intent Classification
# =============================================================================

class TestWizardIntentClassification:
    """classify_intent() must recognize wizard setup phrases."""

    def test_setup_ontology_phrase(self, core: ChiefOfStaffCore):
        intent = core.classify_intent("setup ontology")
        assert intent == "setup_ontology"

    def test_ontology_setup_phrase(self, core: ChiefOfStaffCore):
        intent = core.classify_intent("ontology setup wizard")
        assert intent == "setup_ontology"

    def test_setup_aliases(self, core: ChiefOfStaffCore):
        """@alias routing should also work for setup intents."""
        intent = core.classify_intent("@setup")
        assert intent == "setup_ontology"

    def test_setup_ontology_with_context(self, core: ChiefOfStaffCore):
        intent = core.classify_intent("I need to setup ontology for invoice processing")
        assert intent == "setup_ontology"

    def test_case_insensitive(self, core: ChiefOfStaffCore):
        intent = core.classify_intent("Setup Ontology Now")
        assert intent == "setup_ontology"

    def test_wizard_in_sentence(self, core: ChiefOfStaffCore):
        intent = core.classify_intent("Let me start the ontology setup wizard for AP")
        assert intent == "setup_ontology"


# =============================================================================
# Existing Intent Backward Compatibility
# =============================================================================

class TestExistingIntentsBackwardCompat:
    """Existing intent classifications must NOT be broken by the wizard changes."""

    EXISTING_TESTS = [
        # Discovery
        ("discovery", "discovery"),
        ("discover new customer", "discovery"),
        ("ingest these documents", "discovery"),
        ("upload transcript", "discovery"),
        # Ontology mapping ("governance" doesn't match "govern" due to \b boundary)
        ("map these entities", "ontology_mapping"),
        ("ontology mapping needed", "ontology_mapping"),
        ("canonical objects", "ontology_mapping"),
        # Truth analysis
        ("truth analysis needed", "truth_analysis"),
        ("stuck on this analysis", "truth_analysis"),
        ("overdue items", "truth_analysis"),
        ("risk assessment", "truth_analysis"),
        # Note: "risk" is truth_analysis, "risk.analysis" is strategy — first match wins
        # Workflow design
        ("build workflow", "workflow_design"),
        ("workflow automation", "workflow_design"),
        ("sop for this process", "workflow_design"),
        ("automate this process", "workflow_design"),
        # Governance review ("governance" ≠ "govern" with \b boundary — falls to default)
        ("approve this", "governance_review"),
        ("activation required", "governance_review"),
        ("deploy to production", "governance_review"),
        # Handoff
        ("handoff completed", "handoff"),
        ("summary report", "handoff"),
        ("export data", "handoff"),
        # Strategy
        ("strategy session", "strategy"),
        ("business objective", "strategy"),
        ("change strategy", "strategy"),
        ("evaluate solution", "strategy"),
        # Note: "current state analysis" has space, not dot — falls to default
        # Note: "risk analysis" matches "risk" first → truth_analysis
    ]

    @pytest.mark.parametrize("message,expected_intent", EXISTING_TESTS)
    def test_existing_intents_unchanged(
        self, core: ChiefOfStaffCore, message: str, expected_intent: str
    ):
        assert core.classify_intent(message) == expected_intent

    # Test @alias routing still works
    @pytest.mark.parametrize("alias,expected_intent", [
        ("@discover translate this", "discovery"),
        ("@map these entities", "ontology_mapping"),
        ("@truth find patterns", "truth_analysis"),
        ("@build a workflow", "workflow_design"),
        ("@govern my system", "governance_review"),
        ("@strategy overview please", "strategy"),
    ])
    def test_alias_routing_unchanged(
        self, core: ChiefOfStaffCore, alias: str, expected_intent: str
    ):
        assert core.classify_intent(alias) == expected_intent


# =============================================================================
# Wizard Route Resolution
# =============================================================================

class TestWizardRouteResolution:
    """route() must map setup_ontology to DiscoveryWorkflow."""

    def test_setup_ontology_routes_to_discovery(self, core: ChiefOfStaffCore):
        from src.workflows.discovery_workflow import DiscoveryWorkflow
        workflows = core.route("setup_ontology")
        assert DiscoveryWorkflow in workflows
        assert len(workflows) == 1

    def test_existing_routes_unchanged(self, core: ChiefOfStaffCore):
        from src.workflows.discovery_workflow import DiscoveryWorkflow
        from src.workflows.ontology_mapping_workflow import OntologyMappingWorkflow
        from src.workflows.truth_analysis_workflow import TruthAnalysisWorkflow
        from src.workflows.workflow_builder_workflow import WorkflowBuilderWorkflow
        from src.workflows.governance_workflow import GovernanceWorkflow
        from src.workflows.strategy_workflow import StrategyWorkflow

        assert core.route("discovery") == [DiscoveryWorkflow]
        assert core.route("ontology_mapping") == [OntologyMappingWorkflow]
        assert core.route("truth_analysis") == [TruthAnalysisWorkflow]
        assert core.route("workflow_design") == [WorkflowBuilderWorkflow]
        assert core.route("governance_review") == [GovernanceWorkflow]
        assert core.route("strategy") == [StrategyWorkflow]


# =============================================================================
# Setup Intent in Orchestration Context
# =============================================================================

class TestWizardOrchestration:
    """Verify wizard intent flows through full orchestration."""

    def test_setup_intent_produces_response(self, core: ChiefOfStaffCore):
        """End-to-end orchestration with setup intent should not crash."""
        resp = core.orchestrate(
            tenant_id="test-tenant",
            engagement_id="test-eng",
            message="setup ontology for vendor management",
            workspace_mode="dashboard",
        )
        assert resp.specialist == "ChiefOfStaff"
        assert resp.workflow_name == "ChiefOfStaffWorkflow"
        assert resp.confidence >= 0.5

    def test_setup_intent_sets_discovery_phase(self, core: ChiefOfStaffCore):
        """Phase should be set to discovery for setup_ontology intent."""
        resp = core.orchestrate(
            tenant_id="test-tenant",
            engagement_id="test-eng",
            message="setup ontology for AP",
            workspace_mode="dashboard",
        )
        # The patch should include phase=discovery
        assert resp.engagement_state_patch is not None
        patch = resp.engagement_state_patch
        assert patch.get("phase") == "discovery"
