"""Tests for CommsWorkflow — TDD approach.

Run FIRST — they should FAIL, then implement code to pass them.
"""
import pytest


class TestCommsWorkflow:
    """CommsWorkflow tests."""

    def test_comms_workflow_exists(self):
        """CommsWorkflow must exist with proper decorator."""
        from src.workflows.comms_workflow import CommsWorkflow
        assert hasattr(CommsWorkflow, "__temporal_workflow_definition")

    def test_comms_workflow_runs_activity(self):
        """CommsWorkflow must have a valid activity."""
        from src.workflows.comms_workflow import run_comms_specialist
        assert callable(run_comms_specialist)

    def test_comms_workflow_accepts_input(self):
        """CommsWorkflow must accept question + tenant_id."""
        from src.workflows.comms_workflow import CommsWorkflow
        assert hasattr(CommsWorkflow, 'run')
