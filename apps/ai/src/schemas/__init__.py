"""
Pydantic schemas for TrackGuard v4.2 Phase 3 desk agents.

Export all desk result types for easy importing.
"""
from src.schemas.desk_results import (
    HitlRisk,
    FinanceTaskResult,
    PeopleOpsFinding,
    LegalOpsResult,
    IntelligenceFinding,
    ITRiskAlert,
    KnowledgeManagerResult,
    DeskResult,
)

__all__ = [
    "HitlRisk",
    "FinanceTaskResult",
    "PeopleOpsFinding",
    "LegalOpsResult",
    "IntelligenceFinding",
    "ITRiskAlert",
    "KnowledgeManagerResult",
    "DeskResult",
]
