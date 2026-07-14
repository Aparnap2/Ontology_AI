"""
Pydantic output contracts for all 6 desks in OntologyAI v4.2 Phase 3.

These schemas enforce strict output contracts for all desk agents:
- No jargon in user-facing messages
- Exactly ONE action per result
- Clear urgency and risk levels
- Structured HITL (Human-in-the-Loop) escalation

Usage:
    from src.schemas.desk_results import FinanceTaskResult, HitlRisk
    
    result = FinanceTaskResult(
        task_type="ar_reminder",
        headline="Customer payment due in 3 days",
        what_is_true="Invoice #123 for ₹50,000 is due on March 15",
        do_this="Send payment reminder email to customer",
        urgency="today",
        rupee_impact=50000,
        hitl_risk=HitlRisk.LOW,
        is_good_news=False
    )
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal
from enum import Enum


class HitlRisk(str, Enum):
    """Human-in-the-Loop risk levels for escalation decisions."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# =============================================================================
# Finance Desk Results
# =============================================================================

class FinanceTaskResult(BaseModel):
    """
    Output contract for Finance Desk tasks.
    
    Used by: CFO, Bookkeeper, AR/AP Clerk, Payroll Clerk
    
    Attributes:
        task_type: Type of finance task being performed
        headline: One-line summary (max 10 words, no jargon)
        what_is_true: 2-3 sentences explaining the situation with ₹ amounts
        do_this: Exactly ONE action to take (verb-first, no jargon)
        urgency: When to act (today, this_week, this_month)
        rupee_impact: Financial impact in INR (optional)
        hitl_risk: Escalation risk level
        is_good_news: Whether this is positive news (default: False)
    
    Validation:
        - headline, what_is_true, do_this: No finance jargon allowed
        - headline: Max 10 words
        - do_this: Must be exactly one action (no "and" conjunctions)
    """
    task_type: Literal["ar_reminder", "ap_due", "payroll_prep", "reconciliation"]
    headline: str = Field(..., max_length=120)
    what_is_true: str
    do_this: str
    urgency: Literal["today", "this_week", "this_month"]
    rupee_impact: Optional[int] = None
    hitl_risk: HitlRisk
    is_good_news: bool = False

    @field_validator("headline", "what_is_true", "do_this")
    @classmethod
    def no_jargon(cls, v: str) -> str:
        """Validate that no finance jargon is used in user-facing fields."""
        BANNED_PHRASES = [
            "working capital", "Working Capital",
            "burn rate", "Burn Rate",
        ]
        BANNED_WORDS = [
            "EBITDA", "ebitda",
            "DSO", "dso",
            "bps", "BPS",
            "liquidity", "Liquidity",
            "accrual", "Accrual",
            "amortization", "Amortization",
        ]
        for phrase in BANNED_PHRASES:
            if phrase.lower() in v.lower():
                raise ValueError(f"Jargon detected: '{phrase}'. Use plain language instead.")
        for word in BANNED_WORDS:
            if word.lower() in v.lower():
                raise ValueError(f"Jargon detected: '{word}'. Use plain language instead.")
        return v

    @field_validator("headline")
    @classmethod
    def headline_max_words(cls, v: str) -> str:
        """Validate headline is max 10 words."""
        word_count = len(v.split())
        if word_count > 10:
            raise ValueError(f"Headline must be max 10 words, got {word_count}")
        return v

    @field_validator("do_this")
    @classmethod
    def single_action(cls, v: str) -> str:
        """Validate do_this contains exactly one action."""
        # Check for common conjunctions that indicate multiple actions
        conjunctions = [" and ", ";", " then ", " after that ", " also "]
        for conj in conjunctions:
            if conj in v.lower():
                raise ValueError(f"do_this must be exactly ONE action. Found conjunction: '{conj}'")
        return v


# =============================================================================
# People Desk Results
# =============================================================================

class PeopleOpsFinding(BaseModel):
    """
    Output contract for People Desk findings.
    
    Used by: HR Coordinator, Internal Recruiter
    
    Attributes:
        employee_name: Name of the employee this finding relates to
        event_type: Type of HR event (onboarding, leave, appraisal, offboarding)
        context: Background context (2-3 sentences)
        do_this: Exactly ONE action to take
        hitl_risk: Escalation risk level
    
    Validation:
        - do_this: Must be exactly one action
        - context: No HR jargon, plain language only
    """
    employee_name: str
    event_type: Literal["onboarding", "leave_request", "appraisal", "offboarding"]
    context: str
    do_this: str
    hitl_risk: HitlRisk

    @field_validator("context", "do_this")
    @classmethod
    def no_hr_jargon(cls, v: str) -> str:
        """Validate that no HR jargon is used."""
        BANNED = {
            "PIP", "pip", "Performance Improvement Plan",
            "attrition", "Attrition",
            "headcount", "Headcount",
            "FTE", "fte",
            "onboarding", "Onboarding",  # Allow in event_type, not in messages
            "offboarding", "Offboarding",
        }
        for term in BANNED:
            if term in v:
                raise ValueError(f"HR jargon detected: '{term}'. Use plain language instead.")
        return v

    @field_validator("do_this")
    @classmethod
    def single_action(cls, v: str) -> str:
        """Validate do_this contains exactly one action."""
        conjunctions = [" and ", ";", " then ", " after that ", " also "]
        for conj in conjunctions:
            if conj in v.lower():
                raise ValueError(f"do_this must be exactly ONE action. Found conjunction: '{conj}'")
        return v


# =============================================================================
# Legal Desk Results
# =============================================================================

class LegalOpsResult(BaseModel):
    """
    Output contract for Legal Desk tasks.
    
    Used by: Contracts Coordinator, Compliance Tracker
    
    Attributes:
        document_type: Type of legal document (contract, compliance, policy)
        document_name: Name/title of the specific document
        expiry_date: When the document expires (ISO format, optional)
        action_required: Exactly ONE action to take
        hitl_risk: Escalation risk level
    
    Validation:
        - action_required: Must be exactly one action
        - No legalese in user-facing fields
    """
    document_type: str
    document_name: str
    expiry_date: Optional[str] = None  # ISO format: YYYY-MM-DD
    action_required: str
    hitl_risk: HitlRisk

    @field_validator("action_required")
    @classmethod
    def no_legalese(cls, v: str) -> str:
        """Validate that no legalese is used."""
        BANNED = {
            "heretofore", "Heretofore",
            "whereas", "Whereas",
            "notwithstanding", "Notwithstanding",
            "force majeure", "Force Majeure",
            "indemnification", "Indemnification",
            "liability", "Liability",
            "jurisdiction", "Jurisdiction",
        }
        for term in BANNED:
            if term in v:
                raise ValueError(f"Legalese detected: '{term}'. Use plain language instead.")
        return v

    @field_validator("action_required")
    @classmethod
    def single_action(cls, v: str) -> str:
        """Validate action_required contains exactly one action."""
        conjunctions = [" and ", ";", " then ", " after that ", " also "]
        for conj in conjunctions:
            if conj in v.lower():
                raise ValueError(f"action_required must be exactly ONE action. Found conjunction: '{conj}'")
        return v


# =============================================================================
# Intelligence Desk Results
# =============================================================================

class IntelligenceFinding(BaseModel):
    """
    Output contract for Intelligence Desk findings.
    
    Used by: BI Analyst, Policy Watcher
    
    Attributes:
        insight_type: Type of insight (unit economics, churn, anomaly, policy)
        headline: One-line summary (max 10 words)
        evidence: Data/evidence supporting the insight
        do_this: Exactly ONE action to take
        hitl_risk: Escalation risk level
    
    Validation:
        - headline: Max 10 words
        - do_this: Must be exactly one action
        - No analyst jargon
    """
    insight_type: Literal["unit_economics", "churn_signal", "ops_anomaly", "policy_change"]
    headline: str = Field(..., max_length=120)
    evidence: str
    do_this: str
    hitl_risk: HitlRisk

    @field_validator("headline")
    @classmethod
    def headline_max_words(cls, v: str) -> str:
        """Validate headline is max 10 words."""
        word_count = len(v.split())
        if word_count > 10:
            raise ValueError(f"Headline must be max 10 words, got {word_count}")
        return v

    @field_validator("evidence", "do_this")
    @classmethod
    def no_analyst_jargon(cls, v: str) -> str:
        """Validate that no analyst jargon is used in evidence and do_this."""
        BANNED = {
            "EBITDA", "ebitda",
            "CAC", "cac", "Customer Acquisition Cost",
            "LTV", "ltv", "Lifetime Value",
            "ARR", "arr", "Annual Recurring Revenue",
            "MRR", "mrr", "Monthly Recurring Revenue",
            "burn rate", "Burn Rate",
            "runway", "Runway",
        }
        for term in BANNED:
            if term in v:
                raise ValueError(f"Analyst jargon detected: '{term}'. Use plain language instead.")
        return v

    @field_validator("do_this")
    @classmethod
    def single_action(cls, v: str) -> str:
        """Validate do_this contains exactly one action."""
        conjunctions = [" and ", ";", " then ", " after that ", " also "]
        for conj in conjunctions:
            if conj in v.lower():
                raise ValueError(f"do_this must be exactly ONE action. Found conjunction: '{conj}'")
        return v


# =============================================================================
# IT & Tools Desk Results
# =============================================================================

class ITRiskAlert(BaseModel):
    """
    Output contract for IT & Tools Desk alerts.
    
    Used by: IT Admin
    
    Attributes:
        tool_name: Name of the SaaS tool
        monthly_cost: Monthly cost in INR
        days_unused: Days since last active use
        do_this: Exactly ONE action to take
        hitl_risk: Escalation risk level (default: MEDIUM)
    
    Validation:
        - do_this: Must be exactly one action
        - No IT jargon
    """
    tool_name: str
    monthly_cost: int = Field(..., ge=0)
    days_unused: int = Field(..., ge=0)
    do_this: str
    hitl_risk: HitlRisk = HitlRisk.MEDIUM

    @field_validator("do_this")
    @classmethod
    def no_it_jargon(cls, v: str) -> str:
        """Validate that no IT jargon is used."""
        BANNED = {
            "provision", "Provision",
            "deprovision", "Deprovision",
            "SaaS", "saas",
            "seat", "Seat",  # Allow "Cancel seat" but not technical jargon
            "license", "License",
            "SSO", "sso", "Single Sign-On",
            "MFA", "mfa", "Multi-Factor Authentication",
        }
        for term in BANNED:
            if term in v:
                raise ValueError(f"IT jargon detected: '{term}'. Use plain language instead.")
        return v

    @field_validator("do_this")
    @classmethod
    def single_action(cls, v: str) -> str:
        """Validate do_this contains exactly one action."""
        conjunctions = [" and ", ";", " then ", " after that ", " also "]
        for conj in conjunctions:
            if conj in v.lower():
                raise ValueError(f"do_this must be exactly ONE action. Found conjunction: '{conj}'")
        return v


# =============================================================================
# Admin Desk Results
# =============================================================================

class KnowledgeManagerResult(BaseModel):
    """
    Output contract for Admin Desk knowledge management.
    
    Used by: EA (Executive Assistant), Knowledge Manager
    
    Attributes:
        topic: Topic/subject of the knowledge
        extracted_sop: Extracted Standard Operating Procedure
        neo4j_nodes_added: Number of knowledge graph nodes created
        do_this: Exactly ONE action to take
        hitl_risk: Escalation risk level (default: LOW)
    
    Validation:
        - extracted_sop: Clear, step-by-step instructions
        - do_this: Must be exactly one action
    """
    topic: str
    extracted_sop: str
    neo4j_nodes_added: int = Field(..., ge=0)
    do_this: str
    hitl_risk: HitlRisk = HitlRisk.LOW

    @field_validator("extracted_sop")
    @classmethod
    def sop_must_be_clear(cls, v: str) -> str:
        """Validate SOP is clear and actionable."""
        if len(v) < 20:
            raise ValueError("SOP must be at least 20 characters")
        # Check for step-by-step structure (numbered or bulleted)
        if not any(marker in v for marker in ["1.", "2.", "3.", "-", "*", "•", "Step"]):
            raise ValueError("SOP should have step-by-step structure (numbered or bulleted)")
        return v

    @field_validator("do_this")
    @classmethod
    def single_action(cls, v: str) -> str:
        """Validate do_this contains exactly one action."""
        conjunctions = [" and ", ";", " then ", " after that ", " also "]
        for conj in conjunctions:
            if conj in v.lower():
                raise ValueError(f"do_this must be exactly ONE action. Found conjunction: '{conj}'")
        return v


# =============================================================================
# Union type for all desk results (for Chief of Staff routing)
# =============================================================================

from typing import Union

DeskResult = Union[
    FinanceTaskResult,
    PeopleOpsFinding,
    LegalOpsResult,
    IntelligenceFinding,
    ITRiskAlert,
    KnowledgeManagerResult,
]
