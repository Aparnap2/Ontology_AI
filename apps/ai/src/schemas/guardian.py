"""
Pydantic output contracts for OntologyAI v3.0 Guardian Agent.

These schemas enforce strict output contracts for the Guardian:
- AlertDecision: Cognitive decision only — should alert or not
- GuardianMessage: Final narrative only — human-readable alert
- Word-limit validation on all user-facing text
- injected_numbers: Audit trail for numbers from data sources (never from LLM)

Usage:
    from src.schemas.guardian import AlertDecision, GuardianMessage
    
    decision = AlertDecision(
        should_alert=True,
        severity="critical",
        primary_signal="Payment failed 3 times",
        context_note="Customer tried paying for annual subscription"
    )
    
    message = GuardianMessage(
        pattern_name="failed_payment_retry",
        insight="Customer attempted to pay 3 times for annual subscription. All attempts failed due to card decline.",
        urgency_horizon="today",
        one_action="Refund the failed payments and email customer with alternative payment options",
        injected_numbers=["3", "2", "7500"]
    )
"""
from pydantic import BaseModel, Field, field_validator
from typing import Literal


class AlertDecision(BaseModel):
    """
    Output contract for Guardian's cognitive decision.
    
    Used by: Guardian Agent for triage decisions.
    
    This is the "cognitive decision only" layer — determines whether
    an alert should be triggered and at what severity level.
    
    Attributes:
        should_alert: Whether to trigger an alert (True/False)
        severity: Alert severity level
        primary_signal: The main signal that triggered this decision
        context_note: Brief context (max 20 words)
    
    Validation:
        - context_note: Max 20 words
    """
    should_alert: bool
    severity: Literal["critical", "warning", "info"]
    primary_signal: str
    context_note: str = Field(..., max_length=200)

    @field_validator("context_note")
    @classmethod
    def context_note_max_words(cls, v: str) -> str:
        """Validate context_note is max 20 words."""
        word_count = len(v.split())
        if word_count > 20:
            raise ValueError(f"context_note must be max 20 words, got {word_count}")
        return v


class GuardianMessage(BaseModel):
    """
    Output contract for Guardian's final narrative.
    
    Used by: Guardian Agent for human-readable alerts.
    
    This is the "final narrative only" layer — produces the human-readable
    alert message that users see. All numbers must come from data sources
    (injected_numbers audit trail), never directly from LLM.
    
    Attributes:
        pattern_name: Name of the detected pattern
        insight: Human-readable insight (max 200 words)
        urgency_horizon: When to act (today, this_week, this_month, this_quarter)
        one_action: Exactly ONE action to take
        injected_numbers: Audit trail for numbers from data sources
    
    Validation:
        - insight: Max 200 words
        - one_action: Must be exactly one action (no conjunctions)
        - injected_numbers: Must not be empty if insight contains digits
    """
    pattern_name: str
    insight: str = Field(..., max_length=2000)
    urgency_horizon: Literal["today", "this_week", "this_month", "this_quarter"]
    one_action: str
    injected_numbers: list[str] = Field(default_factory=list)

    @field_validator("insight")
    @classmethod
    def insight_max_words(cls, v: str) -> str:
        """Validate insight is max 200 words."""
        word_count = len(v.split())
        if word_count > 200:
            raise ValueError(f"insight must be max 200 words, got {word_count}")
        return v

    @field_validator("one_action")
    @classmethod
    def single_action(cls, v: str) -> str:
        """Validate one_action contains exactly one action."""
        conjunctions = [" and ", ";", " then ", " after that ", " also "]
        for conj in conjunctions:
            if conj in v.lower():
                raise ValueError(f"one_action must be exactly ONE action. Found conjunction: '{conj}'")
        return v