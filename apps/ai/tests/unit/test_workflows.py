"""
Unit tests for Temporal Workflows and Activities - Day 5.

Tests cover:
- Worker registration and imports
- Workflow importability and structure
- Activity input validation and return values
- Slack message sending

Run with:
  uv run pytest tests/unit/test_workflows.py -v --timeout=30 --asyncio-mode=auto
"""
import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment variables before importing activities
os.environ["SLACK_WEBHOOK_URL"] = ""
os.environ["SLACK_BOT_TOKEN"] = ""
os.environ["SLACK_CHANNEL"] = "#test"

TENANT = "test-workflow-tenant"


# =============================================================================
# TestWorkerRegistration (7 tests)
# =============================================================================


class TestWorkerRegistration:
    """Tests for worker registration and imports."""

    def test_worker_module_importable(self):
        """Test that worker module can be imported."""
        from src import worker

        assert worker is not None
        assert hasattr(worker, "create_worker")
        assert hasattr(worker, "main")
        assert hasattr(worker, "TASK_QUEUE")

    def test_worker_task_queue_configured(self):
        """Test that worker has correct task queue."""
        from src.worker import TASK_QUEUE

        assert TASK_QUEUE == "TRACKGUARD-MAIN-QUEUE"

    def test_pulse_workflow_importable(self):
        """Test that PulseWorkflow can be imported."""
        from src.workflows.pulse_workflow import PulseWorkflow

        assert PulseWorkflow is not None
        assert hasattr(PulseWorkflow, "run")

    def test_investor_workflow_importable(self):
        """Test that InvestorWorkflow can be imported."""
        from src.workflows.investor_workflow import InvestorWorkflow

        assert InvestorWorkflow is not None
        assert hasattr(InvestorWorkflow, "run")

    def test_qa_workflow_importable(self):
        """Test that QAWorkflow can be imported."""
        from src.workflows.qa_workflow import QAWorkflow

        assert QAWorkflow is not None
        assert hasattr(QAWorkflow, "run")

    def test_all_activities_importable(self):
        """Test that all activities can be imported."""
        from src.activities.run_pulse_agent import run_pulse_agent
        from src.activities.run_anomaly_agent import run_anomaly_agent
        from src.activities.run_investor_agent import run_investor_agent
        from src.activities.run_qa_agent import run_qa_agent
        from src.activities.send_slack_message import send_slack_message

        assert run_pulse_agent is not None
        assert run_anomaly_agent is not None
        assert run_investor_agent is not None
        assert run_qa_agent is not None
        assert send_slack_message is not None

    def test_activities_have_correct_names(self):
        """Test that activities have correct Temporal names."""
        from src.activities.run_pulse_agent import run_pulse_agent
        from src.activities.run_anomaly_agent import run_anomaly_agent
        from src.activities.run_investor_agent import run_investor_agent
        from src.activities.run_qa_agent import run_qa_agent
        from src.activities.send_slack_message import send_slack_message

        # Check that activities have __temporal_activity_definition
        assert hasattr(run_pulse_agent, "__temporal_activity_definition")
        assert hasattr(run_anomaly_agent, "__temporal_activity_definition")
        assert hasattr(run_investor_agent, "__temporal_activity_definition")
        assert hasattr(run_qa_agent, "__temporal_activity_definition")
        assert hasattr(send_slack_message, "__temporal_activity_definition")


# =============================================================================
# TestPulseWorkflowLogic (3 tests)
# =============================================================================


class TestPulseWorkflowLogic:
    """Tests for PulseWorkflow logic."""

    @pytest.mark.asyncio
    async def test_pulse_workflow_missing_tenant_id(self):
        """Test that PulseWorkflow returns error on missing tenant_id."""
        from src.workflows.pulse_workflow import PulseWorkflow

        workflow = PulseWorkflow()
        result = await workflow.run({"tenant_id": ""})

        assert result["ok"] is False
        assert "error" in result
        assert "tenant_id is required" in result["error"]

    @pytest.mark.asyncio
    async def test_pulse_workflow_returns_correct_structure(self):
        """Test that PulseWorkflow returns correct structure on success."""
        from src.workflows.pulse_workflow import PulseWorkflow

        # Mock the activities
        mock_pulse_result = {
            "ok": True,
            "tenant_id": TENANT,
            "metrics": {"revenue": 1000},
            "narrative": "Test narrative",
            "slack_blocks": [],
        }
        mock_slack_result = {"ok": True, "message_id": "123"}

        with patch("src.workflows.pulse_workflow.workflow") as mock_workflow:
            mock_workflow.execute_activity = AsyncMock(side_effect=[mock_pulse_result, mock_slack_result])
            mock_workflow.logger = MagicMock()

            workflow = PulseWorkflow()
            result = await workflow.run({"tenant_id": TENANT})

            assert result["ok"] is True
            assert result["tenant_id"] == TENANT
            assert "pulse_result" in result
            assert "slack_result" in result

    @pytest.mark.asyncio
    async def test_pulse_workflow_handles_activity_failure(self):
        """Test that PulseWorkflow handles PulseAgent failure."""
        from src.workflows.pulse_workflow import PulseWorkflow

        # Mock the activities - PulseAgent fails
        mock_pulse_result = {"ok": False, "error": "Test error"}
        mock_slack_result = {"ok": True}

        with patch("src.workflows.pulse_workflow.workflow") as mock_workflow:
            mock_workflow.execute_activity = AsyncMock(side_effect=[mock_pulse_result, mock_slack_result])
            mock_workflow.logger = MagicMock()

            workflow = PulseWorkflow()
            result = await workflow.run({"tenant_id": TENANT})

            assert result["ok"] is False
            assert result["error"] == "Test error"


# =============================================================================
# TestQAWorkflowLogic (2 tests)
# =============================================================================


class TestQAWorkflowLogic:
    """Tests for QAWorkflow logic."""

    @pytest.mark.asyncio
    async def test_qa_workflow_missing_question(self):
        """Test that QAWorkflow returns error on missing question."""
        from src.workflows.qa_workflow import QAWorkflow

        workflow = QAWorkflow()
        result = await workflow.run({"tenant_id": TENANT, "question": ""})

        assert result["ok"] is False
        assert "error" in result
        assert "question is required" in result["error"]

    @pytest.mark.asyncio
    async def test_qa_workflow_returns_correct_structure(self):
        """Test that QAWorkflow returns correct structure on success."""
        from src.workflows.qa_workflow import QAWorkflow

        # Mock the activities
        mock_qa_result = {
            "ok": True,
            "tenant_id": TENANT,
            "question": "What is revenue?",
            "answer": "Revenue is $1000",
            "slack_blocks": [],
        }
        mock_slack_result = {"ok": True, "message_id": "456"}

        with patch("src.workflows.chief_of_staff_workflow.workflow") as mock_workflow:
            mock_workflow.execute_activity = AsyncMock(side_effect=[mock_qa_result, mock_slack_result])
            mock_workflow.logger = MagicMock()

            workflow = QAWorkflow()
            result = await workflow.run({"tenant_id": TENANT, "question": "What is revenue?"})

            assert result["ok"] is True
            assert result["tenant_id"] == TENANT
            assert result["question"] == "What is revenue?"
            assert "qa_result" in result
            assert "slack_result" in result


# =============================================================================
# TestSendSlackActivity (2 tests)
# =============================================================================


class TestSendSlackActivity:
    """Tests for send_slack_message activity."""

    @pytest.mark.asyncio
    async def test_send_slack_message_empty_text(self):
        """Test that activity returns error on empty text."""
        from src.activities.send_slack_message import send_slack_message

        result = await send_slack_message("")

        assert result["ok"] is False
        assert "error" in result
        assert "empty" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_send_slack_message_no_config_simulates_success(self):
        """Test that activity simulates success when no Slack config."""
        from src.activities.send_slack_message import send_slack_message

        # Ensure no Slack config is set
        with patch.dict(os.environ, {"SLACK_WEBHOOK_URL": "", "SLACK_BOT_TOKEN": ""}):
            result = await send_slack_message("Test message")

            assert result["ok"] is True
            assert "message_id" in result
            assert "simulated" in result["message_id"]
