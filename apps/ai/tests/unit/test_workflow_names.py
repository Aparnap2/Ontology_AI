"""Tests for TrackGuard V4.1 workflow renames — TDD approach.

Tests verify new canonical workflow names exist and old names
resolve via backward-compat aliases. Run FIRST — they should FAIL.
"""
import pytest


class TestChiefOfStaffWorkflow:
    """ChiefOfStaffWorkflow replaces QAWorkflow."""

    def test_chief_of_staff_workflow_exists(self):
        """ChiefOfStaffWorkflow must exist with proper decorator."""
        from src.workflows.chief_of_staff_workflow import ChiefOfStaffWorkflow
        assert hasattr(ChiefOfStaffWorkflow, "__temporal_workflow_definition")

    def test_chief_of_staff_workflow_runs_activity(self):
        """ChiefOfStaffWorkflow must import run_qa_agent activity."""
        from src.workflows.chief_of_staff_workflow import run_qa_agent
        assert callable(run_qa_agent)

    def test_qa_workflow_backward_compat_alias(self):
        """Old QAWorkflow name must still resolve as alias."""
        from src.workflows.qa_workflow import QAWorkflow
        from src.workflows.chief_of_staff_workflow import ChiefOfStaffWorkflow
        assert QAWorkflow is ChiefOfStaffWorkflow


class TestFPAWorkflow:
    """FPAWorkflow replaces FinanceWorkflow."""

    def test_fpa_workflow_exists(self):
        """FPAWorkflow must exist with proper decorator."""
        from src.workflows.fpa_workflow import FPAWorkflow
        assert hasattr(FPAWorkflow, "__temporal_workflow_definition")

    def test_fpa_workflow_runs_activity(self):
        """FPAWorkflow must import run_finance_guardian activity."""
        from src.workflows.fpa_workflow import run_finance_guardian
        assert callable(run_finance_guardian)

    def test_finance_workflow_backward_compat(self):
        """Old FinanceWorkflow must resolve as alias."""
        from src.workflows.finance_workflow import FinanceWorkflow
        from src.workflows.fpa_workflow import FPAWorkflow
        assert FinanceWorkflow is FPAWorkflow


class TestGrowthAnalyticsWorkflow:
    """GrowthAnalyticsWorkflow replaces DataWorkflow."""

    def test_growth_analytics_workflow_exists(self):
        """GrowthAnalyticsWorkflow must exist with proper decorator."""
        from src.workflows.growth_analytics_workflow import GrowthAnalyticsWorkflow
        assert hasattr(GrowthAnalyticsWorkflow, "__temporal_workflow_definition")

    def test_growth_analytics_workflow_runs_activity(self):
        """GrowthAnalyticsWorkflow must import run_bi_analyst activity."""
        from src.workflows.growth_analytics_workflow import run_bi_analyst
        assert callable(run_bi_analyst)

    def test_data_workflow_backward_compat(self):
        """Old DataWorkflow must resolve as alias."""
        from src.workflows.data_workflow import DataWorkflow
        from src.workflows.growth_analytics_workflow import GrowthAnalyticsWorkflow
        assert DataWorkflow is GrowthAnalyticsWorkflow


class TestReliabilityWorkflow:
    """ReliabilityWorkflow replaces OpsWorkflow."""

    def test_reliability_workflow_exists(self):
        """ReliabilityWorkflow must exist with proper decorator."""
        from src.workflows.reliability_workflow import ReliabilityWorkflow
        assert hasattr(ReliabilityWorkflow, "__temporal_workflow_definition")

    def test_reliability_workflow_runs_activity(self):
        """ReliabilityWorkflow must import run_ops_watch activity."""
        from src.workflows.reliability_workflow import run_ops_watch
        assert callable(run_ops_watch)

    def test_ops_workflow_backward_compat(self):
        """Old OpsWorkflow must resolve as alias."""
        from src.workflows.ops_workflow import OpsWorkflow
        from src.workflows.reliability_workflow import ReliabilityWorkflow
        assert OpsWorkflow is ReliabilityWorkflow
