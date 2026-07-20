"""OntologyAI V6 — BABOK Strategy Artifact models (PRD §8.3 / §16.3 extension).

Extends the V5.1 pipeline with:
- CurrentStateDescription
- BusinessObjectives / FutureStateDescription
- RiskAnalysisResults
- ChangeStrategy / SolutionScope

These are produced by the StrategyWorkflow and consumed by WorkflowBuilder
and GovernanceGate. They follow the BaseArtifact pattern from ba_artifact.py.
"""
from __future__ import annotations

from typing import Any

from pydantic import Field

from src.schemas.ba_artifact import BaseArtifact


class CurrentStateDescription(BaseArtifact):
    """Describes the current state of the business domain (BABOK §3.2).

    Produced from discovery notes + ontology snapshot + truth findings.
    """

    summary: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    known_bottlenecks: list[str] = Field(default_factory=list)
    missing_owners: list[str] = Field(default_factory=list)
    overdue_items: list[str] = Field(default_factory=list)
    linked_discovery_refs: list[str] = Field(default_factory=list)

    @classmethod
    def from_truth_findings(
        cls,
        artifact_id: str,
        truth_findings: list[dict],
        discovery_refs: list[str],
    ) -> "CurrentStateDescription":
        """Deterministically build a CurrentStateDescription from truth findings.

        No LLM — purely structural mapping.
        """
        weaknesses: list[str] = []
        bottlenecks: list[str] = []
        missing: list[str] = []
        overdue: list[str] = []

        for f in truth_findings:
            summary = f.get("summary", "")
            kind = f.get("kind", "")
            if kind == "missing_owner":
                missing.append(summary)
            elif kind == "overdue_money_event":
                overdue.append(summary)
            elif kind == "blocked_engagement":
                bottlenecks.append(summary)
            else:
                weaknesses.append(summary)

        return cls(
            artifact_id=artifact_id,
            summary=f"Current state based on {len(truth_findings)} truth finding(s)",
            weaknesses=weaknesses,
            known_bottlenecks=bottlenecks,
            missing_owners=missing,
            overdue_items=overdue,
            linked_discovery_refs=discovery_refs,
            provenance=[f"truth:{f.get('target_id','?')}" for f in truth_findings],
            producer="StrategyWorkflow",
        )


class BusinessObjectives(BaseArtifact):
    """Business objectives and future state description (BABOK §3.3 / §3.4).

    Captures the desired outcome, goals, and future state vision.
    """

    goal_summary: str
    objectives: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    linked_current_state_id: str = ""
    desired_outcome: str = ""

    @classmethod
    def from_operator_goal(
        cls,
        artifact_id: str,
        operator_goal: str,
        current_state: CurrentStateDescription,
    ) -> "BusinessObjectives":
        """Build from operator goal + current state."""
        return cls(
            artifact_id=artifact_id,
            goal_summary=operator_goal,
            objectives=[f"Resolve {b}" for b in current_state.known_bottlenecks],
            success_criteria=[f"{b} resolved" for b in current_state.known_bottlenecks],
            linked_current_state_id=current_state.artifact_id,
            desired_outcome=operator_goal,
            provenance=current_state.provenance,
            producer="StrategyWorkflow",
        )


class RiskAnalysisResults(BaseArtifact):
    """Risk analysis results (BABOK §3.5).

    Captures risks identified from current state + future state gap.
    """

    risks: list[dict] = Field(default_factory=list)
    linked_current_state_id: str = ""
    linked_objectives_id: str = ""

    @classmethod
    def from_gaps(
        cls,
        artifact_id: str,
        linked_current_state_id: str,
        linked_objectives_id: str,
        bottlenecks: list[str],
        missing_owners: list[str],
        provenance: list[str],
    ) -> "RiskAnalysisResults":
        """Deterministically build from bottlenecks and missing owners.

        Bottleneck gaps become high-severity risks; missing-owner gaps
        become medium-severity risks. No LLM — purely structural mapping.
        """
        risks: list[dict] = []
        for b in bottlenecks:
            risks.append(
                {"risk_type": "bottleneck", "description": b, "severity": "high"}
            )
        for m in missing_owners:
            risks.append(
                {"risk_type": "missing_owner", "description": m, "severity": "medium"}
            )
        return cls(
            artifact_id=artifact_id,
            linked_current_state_id=linked_current_state_id,
            linked_objectives_id=linked_objectives_id,
            risks=risks,
            provenance=provenance,
            producer="StrategyWorkflow",
        )


class ChangeStrategy(BaseArtifact):
    """Change strategy and solution scope (BABOK §3.6 / §3.7).

    Defines the approach for moving from current to future state,
    including the solution scope boundary.
    """

    approach: str = ""
    solution_scope: str = ""
    key_milestones: list[str] = Field(default_factory=list)
    linked_risk_id: str = ""
    linked_objectives_id: str = ""
    linked_current_state_id: str = ""

    @classmethod
    def from_analysis(
        cls,
        artifact_id: str,
        approach: str,
        solution_scope: str,
        key_milestones: list[str],
        linked_risk_id: str,
        linked_objectives_id: str,
        linked_current_state_id: str,
        provenance: list[str],
    ) -> "ChangeStrategy":
        """Deterministically build a ChangeStrategy from analysis inputs.

        No LLM — purely structural mapping.
        """
        return cls(
            artifact_id=artifact_id,
            approach=approach,
            solution_scope=solution_scope,
            key_milestones=key_milestones,
            linked_risk_id=linked_risk_id,
            linked_objectives_id=linked_objectives_id,
            linked_current_state_id=linked_current_state_id,
            provenance=provenance,
            producer="StrategyWorkflow",
        )


class SolutionEvaluationReport(BaseArtifact):
    """Solution evaluation report (BABOK §3.8).

    Records expected vs actual outcomes for a deployed or planned workflow.
    """

    expected_outcome: str = ""
    actual_outcome: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    linked_strategy_id: str = ""
    linked_workflow_id: str = ""

    @classmethod
    def from_outcome(
        cls,
        artifact_id: str,
        expected_outcome: str,
        actual_outcome: str,
        metrics: dict[str, Any],
        limitations: list[str],
        recommended_actions: list[str],
        linked_strategy_id: str,
        linked_workflow_id: str,
        provenance: list[str],
    ) -> "SolutionEvaluationReport":
        """Deterministically build a SolutionEvaluationReport from outcome data.

        No LLM — purely structural mapping.
        """
        return cls(
            artifact_id=artifact_id,
            expected_outcome=expected_outcome,
            actual_outcome=actual_outcome,
            metrics=metrics,
            limitations=limitations,
            recommended_actions=recommended_actions,
            linked_strategy_id=linked_strategy_id,
            linked_workflow_id=linked_workflow_id,
            provenance=provenance,
            producer="StrategyWorkflow",
        )
