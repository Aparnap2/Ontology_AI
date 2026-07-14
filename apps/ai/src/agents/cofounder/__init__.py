"""Co-founder Agent for OntologyAI V3.0.

This module provides the manager layer that orchestrates Employee Agents:
- router.py: routes messages to employee agents
- reflector.py: reads founder response, converts to score
- curator.py: updates Graphiti playbook
- correlation.py: cross-signal detection + synthesis
- joint_council.py: Mantriparishad — cross-domain alert council
- arbiter.py: Nyayadish — inter-agent conflict resolution

PRD Reference: Section 789-793, 220-261
"""
from .router import Router, route_message
from .reflector import Reflector, score_founder_response
from .curator import Curator, update_playbook
from .correlation import CorrelationAgent, detect_correlation
from .joint_council import AlertCouncil, AlertCouncilResult
from .arbiter import ConflictResolver, ArbitrationResult

__all__ = [
    "Router",
    "route_message",
    "Reflector",
    "score_founder_response",
    "Curator",
    "update_playbook",
    "CorrelationAgent",
    "detect_correlation",
    "AlertCouncil",
    "AlertCouncilResult",
    "ConflictResolver",
    "ArbitrationResult",
]