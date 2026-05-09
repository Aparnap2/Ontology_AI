"""
LangGraph compilation for AnomalyAgent.

Graph topology:
  detect_anomaly → (conditional) → retrieve_anomaly_memory →
  generate_explanation → generate_action → build_slack_message →
  send_slack → END

If detect_anomaly finds no anomaly, graph exits immediately.
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from src.agents.anomaly.state import AnomalyState
from src.agents.anomaly.nodes import (
    detect_anomaly_node,
    retrieve_anomaly_memory,
    generate_explanation,
    generate_action,
    build_slack_message,
    send_slack,
)


def build_anomaly_graph() -> StateGraph:
    graph = StateGraph(AnomalyState)

    # Add nodes
    graph.add_node("detect_anomaly",          detect_anomaly_node)
    graph.add_node("retrieve_anomaly_memory", retrieve_anomaly_memory)
    graph.add_node("generate_explanation",    generate_explanation)
    graph.add_node("generate_action",         generate_action)
    graph.add_node("build_slack_message",     build_slack_message)
    graph.add_node("send_slack",              send_slack)

    # Entry point
    graph.set_entry_point("detect_anomaly")

    # Conditional: if no anomaly, skip to END
    graph.add_conditional_edges(
        "detect_anomaly",
        lambda s: "alert" if s.get("should_alert") else "no_alert",
        {
            "alert":    "retrieve_anomaly_memory",
            "no_alert": END,
        },
    )

    # Sequential edges after detection
    graph.add_edge("retrieve_anomaly_memory", "generate_explanation")
    graph.add_edge("generate_explanation",    "generate_action")
    graph.add_edge("generate_action",         "build_slack_message")
    graph.add_edge("build_slack_message",     "send_slack")
    graph.add_edge("send_slack",              END)

    return graph.compile()


# Module-level compiled graph
anomaly_graph = build_anomaly_graph()
