"""
Pydantic schemas for OntologyAI v4.2 Phase 3 desk agents.

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

from src.schemas.engagement_state import EngagementState, merge_patch
from src.schemas.specialist_response import SpecialistResponse
from src.schemas.workflow_spec import WorkflowSpec
from src.schemas.sop import SOP, SOPStep
from src.schemas.ba_artifact import BaseArtifact, ArtifactLifecycleStatus
from src.schemas.strategy_artifacts import (
    BusinessObjectives,
    ChangeStrategy,
    CurrentStateDescription,
    RiskAnalysisResults,
    SolutionEvaluationReport,
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
    "EngagementState",
    "merge_patch",
    "SpecialistResponse",
    "WorkflowSpec",
    "SOP",
    "SOPStep",
    "BaseArtifact",
    "ArtifactLifecycleStatus",
    "BusinessObjectives",
    "ChangeStrategy",
    "CurrentStateDescription",
    "RiskAnalysisResults",
    "SolutionEvaluationReport",
]
