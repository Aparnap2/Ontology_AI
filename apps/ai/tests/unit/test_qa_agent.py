"""
Unit tests for QAAgent stub.

Tests cover:
  - QAState TypedDict structure
  - QAGraph dataclass structure
  - No LLM calls (stub = no-op)

All tests run in MOCK MODE (no real API calls).
"""
from __future__ import annotations


TENANT = "test-qa-tenant-unit"


class TestQAState:
    """Tests for QAState TypedDict structure."""

    def test_qa_state_creation_empty(self):
        """QAState can be created with no fields (all optional)."""
        from src.agents.qa.state import QAState

        state: QAState = {}
        assert isinstance(state, dict)
        assert len(state) == 0

    def test_qa_state_with_tenant_id(self):
        """QAState accepts tenant_id field."""
        from src.agents.qa.state import QAState

        state: QAState = {"tenant_id": TENANT}
        assert state["tenant_id"] == TENANT

    def test_qa_state_with_all_fields(self):
        """QAState accepts all defined fields."""
        from src.agents.qa.state import QAState

        state: QAState = {
            "tenant_id": TENANT,
            "metrics": {"mrr": 1000},
            "memory_context": "context",
            "draft": "draft",
            "narrative": "narrative",
            "slack_message": "message",
            "slack_blocks": [],
            "error": None,
            "retry_count": 0,
            "langfuse_trace_id": "trace-123",
        }
        assert state["tenant_id"] == TENANT
        assert state["metrics"]["mrr"] == 1000
        assert state["memory_context"] == "context"

    def test_qa_state_partial_fields(self):
        """QAState accepts partial fields (not all required)."""
        from src.agents.qa.state import QAState

        state: QAState = {
            "tenant_id": TENANT,
            "metrics": {"arr": 12000},
        }
        assert state["tenant_id"] == TENANT
        assert state["metrics"]["arr"] == 12000


class TestQAGraph:
    """Tests for QAGraph dataclass."""

    def test_qa_graph_creation(self):
        """QAGraph can be created with tenant_id."""
        from src.agents.qa.graph import QAGraph

        graph = QAGraph(tenant_id=TENANT)
        assert graph.tenant_id == TENANT

    def test_qa_graph_requires_tenant_id(self):
        """QAGraph requires tenant_id as constructor argument."""
        from src.agents.qa.graph import QAGraph
        import pytest

        with pytest.raises(TypeError):
            QAGraph()

    def test_qa_graph_module_exports(self):
        """QAGraph is exported from graph module."""
        from src.agents.qa.graph import QAGraph

        assert QAGraph is not None
        assert "tenant_id" in QAGraph.__dataclass_fields__


class TestStubNoOp:
    """Tests verifying stub is a no-op (no LLM calls)."""

    def test_qa_graph_has_no_llm_integration(self):
        """QAGraph stub contains no LLM-related code."""
        import src.agents.qa.graph as graph_module

        source = graph_module.__file__
        with open(source) as f:
            content = f.read()

        # Check for actual LLM integration (imports/calls), not substring "llm"
        # which matches the docstring and internal config.llm module.
        assert "from langchain" not in content.lower()
        assert "import llm" not in content.lower()
        assert "openai" not in content.lower()
        assert "langchain" not in content.lower()

    def test_qa_state_has_no_llm_integration(self):
        """QAState stub contains no LLM-related code."""
        import src.agents.qa.state as state_module

        source = state_module.__file__
        with open(source) as f:
            content = f.read()

        assert "llm" not in content.lower()
        assert "openai" not in content.lower()
        assert "prompt" not in content.lower()

    def test_no_nodes_module_exists(self):
        """Verify nodes module does not exist (not implemented in stub)."""
        import importlib.util

        spec = importlib.util.find_spec("src.agents.qa.nodes")
        assert spec is None, "qa.nodes module should not exist in stub"

    def test_no_prompts_module_exists(self):
        """Verify prompts module does not exist (not implemented in stub)."""
        import importlib.util

        spec = importlib.util.find_spec("src.agents.qa.prompts")
        assert spec is None, "qa.prompts module should not exist in stub"


class TestTypeAnnotations:
    """Tests for type annotations in stub."""

    def test_qa_state_has_typeddict_base(self):
        """QAState inherits from TypedDict."""
        from src.agents.qa.state import QAState

        assert hasattr(QAState, "__annotations__")
        assert hasattr(QAState, "__required_keys__")
        assert hasattr(QAState, "__optional_keys__")

    def test_qa_state_has_tenant_id_str(self):
        """QAState defines tenant_id as str."""
        from src.agents.qa.state import QAState

        hints = QAState.__annotations__
        assert "tenant_id" in hints
        assert hints["tenant_id"] == str

    def test_qa_graph_is_dataclass(self):
        """QAGraph is a dataclass."""
        from src.agents.qa.graph import QAGraph
        from dataclasses import dataclass

        assert hasattr(QAGraph, "__dataclass_fields__")

    def test_qa_graph_tenant_id_is_str(self):
        """QAGraph defines tenant_id as str."""
        from src.agents.qa.graph import QAGraph
        from dataclasses import fields

        tenant_field = next(f for f in fields(QAGraph) if f.name == "tenant_id")
        assert tenant_field.type == str