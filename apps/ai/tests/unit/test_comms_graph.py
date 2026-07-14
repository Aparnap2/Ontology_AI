"""Tests for CommsGraph — TrackGuard V4.1.

Run FIRST — they should FAIL, then implement code to pass them.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestCommsGraph:
    """CommsGraph implementation tests."""

    @pytest.mark.asyncio
    async def test_comms_graph_invoke_accepts_question(self):
        """CommsGraph must accept question + tenant_id input."""
        from src.agents.comms.graph import CommsGraph
        graph = CommsGraph()
        with patch("src.config.llm.chat_completion", return_value="Draft investor update ready."):
            result = await graph.invoke({"question": "Draft an investor update", "tenant_id": "test"})
        assert isinstance(result, dict)
        has_fields = "summary" in result or "response" in result
        assert has_fields, f"Result missing expected fields: {result.keys()}"

    @pytest.mark.asyncio
    async def test_comms_graph_returns_structured_output(self):
        """CommsGraph must return dict matching SpecialistResponse fields."""
        from src.agents.comms.graph import CommsGraph
        graph = CommsGraph()
        with patch("src.config.llm.chat_completion", return_value="Customer update drafted successfully."):
            result = await graph.invoke({"question": "Draft customer update about downtime", "tenant_id": "test"})
        has_summary = "summary" in result or "detailed_response" in result or "response" in result
        assert has_summary, f"Result missing required fields: {result.keys()}"

    @pytest.mark.asyncio
    async def test_comms_graph_handles_empty_question(self):
        """CommsGraph must handle empty question gracefully."""
        from src.agents.comms.graph import CommsGraph
        graph = CommsGraph()
        result = await graph.invoke({"question": "", "tenant_id": "test"})
        assert result is not None
        assert isinstance(result, dict)
        assert result.get("response") == "No question provided."

    def test_comms_graph_uses_system_prompt(self):
        """CommsGraph must have a communications-focused system prompt."""
        from src.agents.comms.graph import CommsGraph
        graph = CommsGraph()
        assert hasattr(graph, "system_prompt"), "CommsGraph missing system_prompt"
        assert "communications" in graph.system_prompt.lower(), (
            f"system_prompt must mention communications, got: {graph.system_prompt}"
        )

    @pytest.mark.asyncio
    async def test_comms_graph_invoke_no_crash_with_missing_tenant(self):
        """CommsGraph must not crash if tenant_id is missing."""
        from src.agents.comms.graph import CommsGraph
        graph = CommsGraph()
        with patch("src.config.llm.chat_completion", return_value="Test response."):
            result = await graph.invoke({"question": "Test question"})
        assert result is not None
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_comms_graph_has_specialist_and_workflow_fields(self):
        """CommsGraph must return specialist and workflow_name fields."""
        from src.agents.comms.graph import CommsGraph
        graph = CommsGraph()
        with patch("src.config.llm.chat_completion", return_value="Test response."):
            result = await graph.invoke({"question": "Test", "tenant_id": "t"})
        assert result.get("specialist") == "Communications"
        assert result.get("workflow_name") == "CommsWorkflow"
