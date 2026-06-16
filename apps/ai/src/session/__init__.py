"""Session Layer for TrackGuard V3.0.

This module provides session management capabilities including:
- Mission state tracking (finance, BI, ops, cross-functional metrics)
- Session context retrieval (recent messages)
- Relevance gating (keyword-based routing)

Per PRD Section 7: #trackguard channel as shared session.
Per PRD Section 11: MissionState shared context object.
Per PRD Section 7: Relevance gate (pure code, zero LLM).
"""

from src.session.mission_state import (
    MissionState,
    get_mission_state,
    update_mission_state,
)
from src.session.context import get_session_context, write_session_message
from src.session.relevance_gate import (
    evaluate_relevance,
    get_triggered_agents,
    RelevanceDecision,
)

__all__ = [
    "MissionState",
    "get_mission_state",
    "update_mission_state",
    "get_session_context",
    "write_session_message",
    "evaluate_relevance",
    "get_triggered_agents",
    "RelevanceDecision",
]