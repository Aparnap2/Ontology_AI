"""
Pydantic schemas for TrackGuard v4.2 Phase 3 desk agents.

Export all desk result types and control plane schemas for easy importing.
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

from src.schemas.control_plane import (
    PolicyDecision,
    RiskScanResult,
    RiskFlag,
    RiskSeverity,
    AgentRegistration,
    AuditEvent,
)

from src.schemas.specialist_response import SpecialistResponse

__all__ = [
    "HitlRisk",
    "FinanceTaskResult",
    "PeopleOpsFinding",
    "LegalOpsResult",
    "IntelligenceFinding",
    "ITRiskAlert",
    "KnowledgeManagerResult",
    "DeskResult",
    "PolicyDecision",
    "RiskScanResult",
    "RiskFlag",
    "RiskSeverity",
    "AgentRegistration",
    "AuditEvent",
    "SpecialistResponse",
]
