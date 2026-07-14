"""OntologyAI HITL — Human-in-the-Loop routing and confidence scoring."""
from src.hitl.manager import HITLManager
from src.hitl.confidence import score_confidence
from src.hitl.approval_queue import request_approval, handle_approval_response, get_pending_approvals

__all__ = [
    "HITLManager",
    "score_confidence",
    "request_approval",
    "handle_approval_response",
    "get_pending_approvals",
]
