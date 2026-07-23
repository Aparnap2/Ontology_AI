"""OntologyAI V6 — StrategyWorkflow (BABOK Phase: Strategy Analysis).

Generates BA strategy artifacts from discovery + truth outputs:
- CurrentStateDescription (from truth findings)
- BusinessObjectives (from operator_goal + current state)
- RiskAnalysisResults (from current state gaps)
- ChangeStrategy (from objectives + risks)
- SolutionEvaluationReport (optional, from planned outcomes)

Design (thin-LLM / fat-deterministic-core, PRD §11):
- All artifact generation is deterministic (no LLM).
- The LLM may propose narrative but is mocked in tests.
- Produces SpecialistResponse patches to engagement_state.
"""
from __future__ import annotations

from typing import Any, Optional

from src.schemas.specialist_response import SpecialistResponse
from src.schemas.ba_artifact import ArtifactLifecycleStatus
from src.schemas.strategy_artifacts import (
    BusinessObjectives,
    ChangeStrategy,
    CurrentStateDescription,
    RiskAnalysisResults,
    SolutionEvaluationReport,
)

_SEQUENCE: int = 0


def _next_id(prefix: str) -> str:
    global _SEQUENCE
    _SEQUENCE += 1
    return f"{prefix}-{_SEQUENCE}"


class StrategyWorkflow:
    """Strategy specialist workflow (BABOK Strategy Analysis)."""

    def __init__(self, llm_client: Optional[Any] = None) -> None:
        self.llm_client = llm_client

    def produce_evaluation(
        self,
        expected_outcome: str,
        actual_outcome: str,
        metrics: dict[str, Any],
        limitations: list[str],
        recommended_actions: list[str],
        linked_strategy_id: str,
        linked_workflow_id: str,
    ) -> SolutionEvaluationReport:
        """Produce a deterministic SolutionEvaluationReport (no LLM)."""
        return SolutionEvaluationReport.from_outcome(
            artifact_id=_next_id("eval"),
            expected_outcome=expected_outcome,
            actual_outcome=actual_outcome,
            metrics=metrics,
            limitations=limitations,
            recommended_actions=recommended_actions,
            linked_strategy_id=linked_strategy_id,
            linked_workflow_id=linked_workflow_id,
            provenance=[f"strategy:{linked_strategy_id}"],
        )

    def run(
        self,
        tenant_id: str,
        engagement_id: str,
        truth_findings: list[dict],
        operator_goal: Optional[str] = None,
        discover_refs: Optional[list[str]] = None,
        planned_outcomes: Optional[dict[str, Any]] = None,
    ) -> SpecialistResponse:
        """Generate strategy artifacts from truth findings and operator goal.

        Args:
            tenant_id: Tenant identifier.
            engagement_id: Engagement identifier.
            truth_findings: List of truth finding dicts (from TruthAnalysisWorkflow).
            operator_goal: Optional operator goal context.
            discover_refs: Optional discovery source references.
            planned_outcomes: Optional dict of outcome data to produce a
                SolutionEvaluationReport. Keys match ``produce_evaluation()``
                params (expected_outcome, actual_outcome, metrics, limitations,
                recommended_actions, linked_strategy_id, linked_workflow_id).

        Returns:
            SpecialistResponse with new artifacts in engagement_state_patch.
        """
        discover_refs = discover_refs or []

        # Use model_copy to respect frozen=True on BaseArtifact.
        current_state = CurrentStateDescription.from_truth_findings(
            artifact_id=_next_id("cs"),
            truth_findings=truth_findings,
            discovery_refs=discover_refs,
        )
        current_state = current_state.model_copy(
            update={"status": ArtifactLifecycleStatus.ANALYZED}
        )

        objectives = BusinessObjectives.from_operator_goal(
            artifact_id=_next_id("bo"),
            operator_goal=operator_goal or "No operator goal provided",
            current_state=current_state,
        )

        risks = RiskAnalysisResults.from_gaps(
            artifact_id=_next_id("ra"),
            linked_current_state_id=current_state.artifact_id,
            linked_objectives_id=objectives.artifact_id,
            bottlenecks=current_state.known_bottlenecks,
            missing_owners=current_state.missing_owners,
            provenance=current_state.provenance,
        )

        strategy = ChangeStrategy.from_analysis(
            artifact_id=_next_id("csg"),
            approach=f"Address {len(current_state.known_bottlenecks)} bottleneck(s) "
            f"and {len(current_state.weaknesses)} weakness(es)",
            solution_scope=f"Engagement {engagement_id} — pilot scope",
            key_milestones=[
                f"Approve strategy for {engagement_id}",
                f"Deploy pilot workflow for {engagement_id}",
                f"Evaluate outcomes for {engagement_id}",
            ],
            linked_risk_id=risks.artifact_id,
            linked_objectives_id=objectives.artifact_id,
            linked_current_state_id=current_state.artifact_id,
            provenance=current_state.provenance,
        )

        patch: dict[str, Any] = {
            "current_state_descriptions": [current_state.model_dump()],
            "business_objectives": [objectives.model_dump()],
            "risk_analyses": [risks.model_dump()],
            "change_strategies": [strategy.model_dump()],
        }

        objects_written = [
            "current_state_descriptions",
            "business_objectives",
            "risk_analyses",
            "change_strategies",
        ]

        # Optional evaluation report production.
        if planned_outcomes:
            evaluation = self.produce_evaluation(**planned_outcomes)
            patch["solution_evaluations"] = [evaluation.model_dump()]
            objects_written.append("solution_evaluations")

        summary = (
            f"Strategy analysis produced {len(current_state.known_bottlenecks)} bottleneck(s), "
            f"{len(objectives.objectives)} objective(s), "
            f"{len(risks.risks)} risk(s), and a change strategy."
        )

        return SpecialistResponse(
            specialist="Strategy",
            workflow_name="StrategyWorkflow",
            summary=summary,
            detailed_response=summary,
            objects_read=["truth_findings"],
            objects_written=objects_written,
            requires_hitl=True,
            engagement_state_patch=patch,
            confidence=0.8,
        )
