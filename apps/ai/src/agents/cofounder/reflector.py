"""Reflector: ACE Reflector for founder response scoring.

Converts founder responses into confidence scores for playbook updates.
PRD Reference: Section 249-257
"""
import logging
from dataclasses import dataclass
from enum import Enum


class ResponseType(Enum):
    """Founder response types."""
    ACKNOWLEDGED = "acknowledged"
    ACTED_ON = "acted_on"
    IGNORED = "ignored"
    DISPUTED = "disputed"
    DISMISSED = "dismissed"


# Score weights per PRD Section 252
RESPONSE_SCORES = {
    ResponseType.ACKNOWLEDGED: 1.0,
    ResponseType.ACTED_ON: 1.5,
    ResponseType.IGNORED: -0.5,
    ResponseType.DISPUTED: -0.5,
    ResponseType.DISMISSED: -1.5,
}


@dataclass
class Reflection:
    response_type: ResponseType
    score: float
    domain: str  # "finance" | "bi" | "ops"


class Reflector:
    """ACE Reflector: converts founder response to score."""
    
    def __init__(self):
        pass
    
    def score(self, response: str, domain: str) -> Reflection:
        """Score founder response.
        
        Args:
            response: Founder's response text or action
            domain: Domain (finance/bi/ops)
            
        Returns:
            Reflection with score
        """
        # Handle empty feedback as neutral (no penalty)
        if not response or not response.strip():
            return Reflection(
                response_type=ResponseType.IGNORED,
                score=0.0,
                domain=domain,
            )
        
        # Determine response type from text
        response_lower = response.lower()
        
        # Check DISPUTED - "already knew" before ACTED_ON
        if any(kw in response_lower for kw in ["already knew", "knew about", "knew this", "disagree", "wrong", "not right", "incorrect"]):
            return self._build_reflection(ResponseType.DISPUTED, domain)
        
        # Check ACTED_ON
        if any(kw in response_lower for kw in ["acted", "doing", "done", "took action"]):
            return self._build_reflection(ResponseType.ACTED_ON, domain)
        
        # Check DISMISSED
        if any(kw in response_lower for kw in ["dismiss", "ignore", "not relevant"]):
            return self._build_reflection(ResponseType.DISMISSED, domain)
        
        # Check ACKNOWLEDGED
        if any(kw in response_lower for kw in ["ok", "thanks", "got it", "understood", "seen"]):
            return self._build_reflection(ResponseType.ACKNOWLEDGED, domain)
        
        # Default: assumed ignored after timeout
        return self._build_reflection(ResponseType.IGNORED, domain)
    
    def _build_reflection(self, response_type: ResponseType, domain: str) -> Reflection:
        return Reflection(
            response_type=response_type,
            score=RESPONSE_SCORES[response_type],
            domain=domain,
        )


def score_founder_response(response: str, domain: str) -> Reflection:
    """Convenience function for scoring."""
    reflector = Reflector()
    return reflector.score(response, domain)


def score_from_button(alert_id: str, response_type: str, score: float) -> None:
    """Score feedback from Slack button interaction.
    
    Args:
        alert_id: The alert/decision being scored
        response_type: Response type (acknowledged/disputed)
        score: Feedback score (+1.0 or -1.0)
    """
    log = logging.getLogger(__name__)
    log.info(f"Button feedback: alert={alert_id}, type={response_type}, score={score}")
    # Placeholder for integration with playbook scoring system
    pass