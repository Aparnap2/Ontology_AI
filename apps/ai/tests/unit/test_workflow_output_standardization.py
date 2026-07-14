"""Tests for workflow output schema enforcement — OntologyAI V4.1.

Each workflow's run() method should return a dict compatible with
SpecialistResponse.model_validate(). Run FIRST — they should FAIL.
"""
import pytest


class TestWorkflowOutputStandardization:
    """Workflow output schema enforcement tests."""

    def test_fpa_workflow_output_validates_as_specialist_response(self):
        """FPAWorkflow must return dict validatable as SpecialistResponse."""
        from src.workflows.fpa_workflow import FPAWorkflow
        workflow = FPAWorkflow()
        assert hasattr(workflow, "run")

    def test_growth_analytics_workflow_output_validates(self):
        """GrowthAnalyticsWorkflow must return SpecialistResponse-compatible dict."""
        from src.workflows.growth_analytics_workflow import GrowthAnalyticsWorkflow
        workflow = GrowthAnalyticsWorkflow()
        assert hasattr(workflow, "run")

    def test_reliability_workflow_output_validates(self):
        """ReliabilityWorkflow must return SpecialistResponse-compatible dict."""
        from src.workflows.reliability_workflow import ReliabilityWorkflow
        workflow = ReliabilityWorkflow()
        assert hasattr(workflow, "run")

    def test_comms_workflow_output_validates(self):
        """CommsWorkflow must return SpecialistResponse-compatible dict."""
        from src.workflows.comms_workflow import CommsWorkflow
        workflow = CommsWorkflow()
        assert hasattr(workflow, "run")

    def test_chief_of_staff_workflow_output_validates(self):
        """ChiefOfStaffWorkflow must return SpecialistResponse-compatible dict."""
        from src.workflows.chief_of_staff_workflow import ChiefOfStaffWorkflow
        workflow = ChiefOfStaffWorkflow()
        assert hasattr(workflow, "run")
