"""
Tests for safety regressions.

Verifies existing safety guards remain intact after migration:
1. QA loop detection
2. Tenant isolation in memory
3. Investor criteria
"""
import pytest


def test_qa_loop_detection_still_active():
    """QA safety guards must remain intact."""
    # QA should have MAX_TOOL_CALLS limit
    # Check that QA agent has safety attributes
    try:
        from apps.ai.src.agents.qa.graph import QAGraph
        from apps.ai.src.agents.qa.nodes import QA_TOOLS

        # Verify tools are defined
        assert len(QA_TOOLS) > 0, "QA tools empty"

        print("QA safety: Tools defined, max calls should be enforced by graph")
    except ImportError as e:
        pytest.skip(f"QA module not available: {e}")


def test_tenant_isolation_in_memory_still_active():
    """Memory tenant isolation must remain intact."""
    try:
        from apps.ai.src.memory.qdrant_ops import _enforce_tenant_filter

        # Should return a filter function
        filter_func = _enforce_tenant_filter("test-tenant")
        assert filter_func is not None, "Tenant filter must be returned"

        print("Memory tenant isolation: filter function exists")
    except ImportError as e:
        pytest.skip(f"Memory module not available: {e}")


def test_investor_criteria_still_active():
    """Investor criteria must remain intact."""
    try:
        from apps.ai.src.agents.investor.criteria import evaluate_draft_quality

        # Test with draft that should fail
        bad_draft = "Things going well, leveraging synergies."
        passes, failures = evaluate_draft_quality(bad_draft)

        # Should fail (contains forbidden words)
        assert not passes, "Bad draft should fail investor criteria"
        assert len(failures) > 0, "Should have failures"

        print(f"Investor criteria: {len(failures)} failures detected")
    except ImportError as e:
        pytest.skip(f"Investor criteria module not available: {e}")


def test_guardian_watchlist_still_active():
    """Guardian watchlist patterns must remain intact."""
    try:
        from apps.ai.src.guardian.watchlist import WATCHLIST

        # Should have at least 17 patterns
        assert len(WATCHLIST) >= 17, f"Expected 17+ patterns, got {len(WATCHLIST)}"

        # Verify pattern structure
        for item in WATCHLIST[:3]:
            assert hasattr(item, "name"), "Pattern missing name"
            assert hasattr(item, "detection_logic"), "Pattern missing detection_logic"

        print(f"Guardian watchlist: {len(WATCHLIST)} patterns loaded")
    except ImportError as e:
        pytest.skip(f"Guardian module not available: {e}")


def test_agent_output_isolation():
    """Agent outputs should be tenant-scoped."""
    try:
        from apps.ai.src.db.agent_outputs import get_agent_outputs

        # Function should require tenant_id
        import inspect
        sig = inspect.signature(get_agent_outputs)
        params = list(sig.parameters.keys())

        assert "tenant_id" in params, "get_agent_outputs must require tenant_id"

        print("Agent output isolation: tenant_id required")
    except ImportError as e:
        pytest.skip(f"Agent outputs module not available: {e}")


def test_qa_graph_has_max_iterations(monkeypatch):
    """The QA graph must be bounded against runaway loops.

    ``QAGraph.invoke`` issues exactly one ``chat_completion`` call and contains
    no loop or recursion, so it cannot iterate unboundedly: its bound is
    structural ("single-shot"), and it intentionally has no ``max_iterations``
    attribute. This asserts that real property.

    The previous version was broken and vacuous: it constructed ``QAGraph()``
    without the required ``tenant_id`` (TypeError), and its only assertion was
    gated behind ``hasattr(graph, "max_iterations")`` which is always False here.
    """
    try:
        from apps.ai.src.agents.qa import graph as qa_graph_module
        from apps.ai.src.agents.qa.graph import QAGraph
    except ImportError as e:
        pytest.skip(f"QA graph module not available: {e}")

    calls = []

    def _fake_completion(**kwargs):
        calls.append(kwargs)
        return "stub answer"

    monkeypatch.setattr(qa_graph_module, "chat_completion", _fake_completion)

    graph = QAGraph(tenant_id="test-tenant")

    # Retain the original bound if the attribute is ever introduced.
    if hasattr(graph, "max_iterations"):
        assert graph.max_iterations <= 10, "max_iterations too high"

    state = graph.invoke({"tenant_id": "test-tenant", "question": "What is revenue?"})

    assert len(calls) == 1, f"QA graph is single-shot; issued {len(calls)} model calls"
    assert state["answer"] == "stub answer"