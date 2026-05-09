"""
LangGraph compilation for PulseAgent.

Graph topology:
  fetch_data → check_data_gate → {no_data: no_data_fallback, has_data: retrieve_memory}
  retrieve_memory → compute_metrics → generate_narrative →
  build_slack_message → send_slack → persist_snapshot → END
  no_data_fallback → build_slack_message (skip metrics, go straight to delivery)
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from src.agents.pulse.state import PulseState
from src.agents.pulse.nodes import (
    fetch_data,
    check_data_gate,
    no_data_fallback,
    retrieve_memory,
    compute_metrics,
    generate_narrative,
    build_slack_message,
    send_slack,
    persist_snapshot,
)


def _route_after_gate(state: PulseState) -> str:
    """Conditional edge router: read gate_result from state and route accordingly."""
    gate_result = state.get("gate_result", "has_data")
    if gate_result == "no_data":
        return "no_data_fallback"
    return "retrieve_memory"


def build_pulse_graph() -> StateGraph:
    """
    Build and compile the PulseAgent LangGraph.

    Includes:
      - Async fetch_data node (parallel integration fetch via asyncio.gather)
      - Data gate node (routes to fallback when no data available)
      - Conditional edge: check_data_gate → {no_data: no_data_fallback, has_data: retrieve_memory}

    Returns:
        Compiled StateGraph ready for invocation
    """
    graph = StateGraph(PulseState)

    # Add nodes
    graph.add_node("fetch_data",          fetch_data)
    graph.add_node("check_data_gate",     check_data_gate)
    graph.add_node("no_data_fallback",    no_data_fallback)
    graph.add_node("retrieve_memory",     retrieve_memory)
    graph.add_node("compute_metrics",     compute_metrics)
    graph.add_node("generate_narrative",  generate_narrative)
    graph.add_node("build_slack_message", build_slack_message)
    graph.add_node("send_slack",          send_slack)
    graph.add_node("persist_snapshot",    persist_snapshot)

    # Entry point
    graph.set_entry_point("fetch_data")

    # Sequential: fetch_data → check_data_gate
    graph.add_edge("fetch_data", "check_data_gate")

    # Conditional edge: check_data_gate → {no_data: no_data_fallback, has_data: retrieve_memory}
    graph.add_conditional_edges(
        "check_data_gate",
        _route_after_gate,
        {
            "no_data_fallback": "no_data_fallback",
            "retrieve_memory": "retrieve_memory",
        },
    )

    # has_data path: retrieve_memory → compute_metrics → generate_narrative
    graph.add_edge("retrieve_memory",     "compute_metrics")
    graph.add_edge("compute_metrics",     "generate_narrative")

    # no_data path: no_data_fallback → build_slack_message (skip metrics)
    graph.add_edge("no_data_fallback",    "build_slack_message")

    # Converge: generate_narrative → build_slack_message
    graph.add_edge("generate_narrative",  "build_slack_message")

    # Delivery: build_slack_message → send_slack → persist_snapshot → END
    graph.add_edge("build_slack_message", "send_slack")
    graph.add_edge("send_slack",          "persist_snapshot")
    graph.add_edge("persist_snapshot",    END)

    return graph.compile()


# Module-level compiled graph (importable by Temporal activities)
pulse_graph = build_pulse_graph()
