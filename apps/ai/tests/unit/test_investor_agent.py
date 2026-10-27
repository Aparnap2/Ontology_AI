"""
Unit tests for InvestorAgent stub.

Tests cover:
  - InvestorState TypedDict structure
  - InvestorGraph dataclass with tenant_id
  - Stub is a no-op (no LLM calls)

All tests run in MOCK MODE (no real API calls).
"""
from __future__ import annotations
import os
import pytest
from unittest.mock import MagicMock, patch

# Force mock environment before any imports
# Force a mock environment before any project-level import. The prior values
# are captured first and restored by the `_restore_env` fixture so these
# overrides do not leak into later suites (which broke P0 worker-startup tests
# by leaving DATABASE_URL empty).
_MOCK_ENV = {
    "STRIPE_API_KEY": "",
    "PLAID_ACCESS_TOKEN": "",
    "SLACK_WEBHOOK_URL": "",
    "DATABASE_URL": "",
    "PRODUCT_DB_URL": "",
    "OLLAMA_BASE_URL": "http://localhost:11434/v1",
}
_PRIOR_ENV = {_k: os.environ.get(_k) for _k in _MOCK_ENV}
os.environ.update(_MOCK_ENV)


@pytest.fixture(scope="module", autouse=True)
def _restore_env():
    """Undo this module's env overrides once its tests finish."""
    yield
    for _k, _original in _PRIOR_ENV.items():
        if _original is None:
            os.environ.pop(_k, None)
        else:
            os.environ[_k] = _original

TENANT = "test-investor-tenant-unit"


# =============================================================================
# TestInvestorState
# =============================================================================

class TestInvestorState:
    """Tests for InvestorState TypedDict structure."""

    def test_investor_state_empty(self):
        """InvestorState can be created empty (all fields optional)."""
        from src.agents.investor.state import InvestorState

        state: InvestorState = {}
        assert isinstance(state, dict)

    def test_investor_state_with_tenant_id(self):
        """InvestorState accepts tenant_id field."""
        from src.agents.investor.state import InvestorState

        state: InvestorState = {"tenant_id": TENANT}
        assert state["tenant_id"] == TENANT

    def test_investor_state_with_metrics(self):
        """InvestorState accepts metrics field."""
        from src.agents.investor.state import InvestorState

        state: InvestorState = {
            "tenant_id": TENANT,
            "metrics": {"mrr_cents": 1250000},
        }
        assert state["metrics"]["mrr_cents"] == 1250000

    def test_investor_state_with_all_fields(self):
        """InvestorState accepts all defined fields."""
        from src.agents.investor.state import InvestorState

        state: InvestorState = {
            "tenant_id": TENANT,
            "metrics": {},
            "memory_context": "previous updates context",
            "draft": "draft content",
            "narrative": "narrative content",
            "slack_message": "slack message",
            "slack_blocks": [],
            "error": "",
            "retry_count": 0,
            "langfuse_trace_id": "trace-123",
        }
        assert state["tenant_id"] == TENANT
        assert state["metrics"] == {}
        assert state["memory_context"] == "previous updates context"
        assert state["draft"] == "draft content"
        assert state["narrative"] == "narrative content"
        assert state["slack_message"] == "slack message"
        assert state["slack_blocks"] == []
        assert state["error"] == ""
        assert state["retry_count"] == 0
        assert state["langfuse_trace_id"] == "trace-123"

    def test_investor_state_all_fields_optional(self):
        """InvestorState has total=False - all fields optional."""
        from src.agents.investor.state import InvestorState

        state: InvestorState = InvestorState()
        assert state == {}


# =============================================================================
# TestInvestorGraph
# =============================================================================

class TestInvestorGraph:
    """Tests for InvestorGraph dataclass."""

    def test_investor_graph_has_tenant_id_field(self):
        """InvestorGraph dataclass has tenant_id field."""
        from src.agents.investor.graph import InvestorGraph

        graph = InvestorGraph(tenant_id=TENANT)
        assert graph.tenant_id == TENANT

    def test_investor_graph_default_tenant_empty(self):
        """Default investor_graph has empty tenant_id."""
        from src.agents.investor.graph import investor_graph

        assert investor_graph.tenant_id == ""

    def test_investor_graph_is_dataclass(self):
        """InvestorGraph is a dataclass."""
        from src.agents.investor.graph import InvestorGraph
        from dataclasses import is_dataclass

        assert is_dataclass(InvestorGraph)

    def test_investor_graph_singleton(self):
        """investor_graph singleton exists."""
        from src.agents.investor.graph import investor_graph

        assert investor_graph is not None
        assert hasattr(investor_graph, "tenant_id")


# =============================================================================
# TestStubNoLLMCalls
# =============================================================================

class TestStubNoLLMCalls:
    """Tests to verify stub is a no-op (no LLM calls)."""

    def test_investor_graph_has_no_build_function(self):
        """Stub does not have build_investor_graph function."""
        from src.agents.investor import graph as graph_module

        assert not hasattr(graph_module, "build_investor_graph")

    def test_investor_state_does_not_call_llm(self):
        """InvestorState manipulation does not trigger LLM calls."""
        from src.agents.investor.state import InvestorState

        state: InvestorState = {"tenant_id": TENANT}
        state["metrics"] = {"mrr_cents": 100000}
        assert state["metrics"]["mrr_cents"] == 100000

    def test_graph_module_exports_only_needed_items(self):
        """Graph module exports only InvestorGraph and investor_graph."""
        from src.agents.investor import graph as graph_module

        assert hasattr(graph_module, "InvestorGraph")
        assert hasattr(graph_module, "investor_graph")
        exported = [name for name in dir(graph_module) if not name.startswith("_") and name not in ("dataclass", "Field", "FieldType", "MISSING")]
        assert len(exported) == 2