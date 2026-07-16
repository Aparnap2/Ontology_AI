"""OntologyAI V5.1 — WorkflowBuilderWorkflow (PRD §8.5 / §16.5).

From truth findings, generates a ``WorkflowSpec`` + ``SOP`` + an
``ExecutableWorkflowDraft`` (status="draft") + a ``PlannedAction`` when
execution/export/activation is proposed.

Design (thin-LLM / fat-deterministic-core, PRD §11):
  * Spec/SOP/draft structure is built deterministically from findings.
  * Runtime target selection (n8n vs custom_agent) is rule-derivable (PRD §17).
  * The LLM may propose narrative phrasing but is mocked in tests.
  * Export payloads are NOT built here — only Governance (via compiler) may.
"""
from __future__ import annotations

from typing import Optional

from src.schemas.specialist_response import SpecialistResponse
from src.schemas.workflow_spec import WorkflowSpec
from src.schemas.sop import SOP, SOPStep
from src.ontology.workflow_drafts import ExecutableWorkflowDraft
from src.ontology.action_types import ActionRegistry


class WorkflowBuilderWorkflow:
    """Workflow Builder specialist workflow (PRD §8.5 / §16.5)."""

    def __init__(self, llm_client: Optional[Any] = None) -> None:
        self.llm_client = llm_client

    def run(
        self,
        tenant_id: str,
        engagement_id: str,
        truth_findings: list[dict],
        ontology_objects: Optional[dict[str, list[dict]]] = None,
        propose_execution: bool = False,
    ) -> SpecialistResponse:
        """Build workflow specs, SOPs, and executable drafts from truth findings.

        Args:
            tenant_id: Tenant identifier.
            engagement_id: Engagement identifier.
            truth_findings: List of truth finding dicts (from TruthAnalysisWorkflow).
            ontology_objects: Optional ontology snapshot for linked_objects.
            propose_execution: If True, emit a PlannedAction for execution/export.

        Returns:
            SpecialistResponse with specialist="WorkflowBuilder" and patches to
            ``workflow_specs``, ``planned_actions``, ``executable_workflow_drafts``.
        """
        ontology_objects = ontology_objects or {}
        specs: list[dict] = []
        drafts: list[dict] = []
        actions: list[dict] = []

        action_worthy = [f for f in truth_findings if f.get("action_worthy")]

        for idx, finding in enumerate(action_worthy):
            spec_id = f"ws-{engagement_id}-{idx}"
            runtime = self._select_runtime(finding)
            spec = self._build_spec(spec_id, finding, ontology_objects, runtime)
            sop = self._build_sop(spec_id, finding)
            spec.sop_id = sop.sop_id
            spec_dict = spec.model_dump()
            spec_dict["sop"] = sop.model_dump()

            draft = ExecutableWorkflowDraft(
                id=f"draft-{spec_id}",
                runtime=runtime,
                name=spec.workflow_name,
                source_workflow_spec_id=spec_id,
                status="draft",
                trigger={"type": "schedule", "on": finding["kind"]},
                inputs=[{"name": "finding", "type": "dict"}],
                steps=self._build_steps(finding),
                decision_points=[{"point": "requires approval?", "if_true": "govern"}],
                approvals=[{"role": "approver", "required": True}],
                side_effects=self._side_effects(finding),
                fallback_paths=[{"on_failure": "notify owner"}],
                success_criteria=[f"resolve {finding['kind']}"],
                source_refs=[f"truth:{finding.get('target_id')}"],
            )

            specs.append(spec_dict)
            drafts.append(draft.model_dump())

            if propose_execution:
                action = ActionRegistry.create(
                    action_type="activate_workflow" if runtime == "n8n" else "create_draft_workflow",
                    target_object_type="Workflow",
                    target_id=draft.id,
                    requested_by="WorkflowBuilder",
                    rationale=f"Deploy workflow to address {finding['kind']}",
                    status="draft",
                    source_refs=[f"truth:{finding.get('target_id')}"],
                    action_id=f"pa-build-{draft.id}",
                )
                actions.append(action.model_dump())

        patch: dict[str, Any] = {
            "workflow_specs": specs,
            "executable_workflow_drafts": drafts,
        }
        if actions:
            patch["planned_actions"] = actions

        summary = (
            f"Built {len(specs)} workflow spec(s) and {len(drafts)} executable "
            f"draft(s) from {len(action_worthy)} action-worthy finding(s)."
        )

        return SpecialistResponse(
            specialist="WorkflowBuilder",
            workflow_name="WorkflowBuilderWorkflow",
            summary=summary,
            detailed_response=summary,
            objects_read=["truth_findings", "ontology_objects"],
            objects_written=["workflow_specs", "executable_workflow_drafts"],
            actions_proposed=[a["id"] for a in actions],
            requires_hitl=any(a.get("requires_approval") for a in actions),
            engagement_state_patch=patch,
            confidence=0.75,
        )

    # ------------------------------------------------------------------
    # Deterministic builders
    # ------------------------------------------------------------------
    def _select_runtime(self, finding: dict) -> str:
        """Rule-derivable runtime selection (PRD §17)."""
        # Connector-heavy / deterministic -> n8n. Dynamic reasoning -> custom_agent.
        if finding["kind"] in ("overdue_money_event", "unacted_message", "orphaned_record"):
            return "n8n"
        return "custom_agent"

    def _build_spec(
        self, spec_id: str, finding: dict, ontology_objects: dict, runtime: str
    ) -> WorkflowSpec:
        target = finding.get("target_id", "unknown")
        return WorkflowSpec(
            workflow_spec_id=spec_id,
            workflow_name=f"Resolve{finding['kind'].title().replace('_', '')}",
            business_goal=f"Address {finding['kind']} on {target}",
            trigger=f"When {finding['kind']} detected for {target}",
            preconditions=[f"{finding['target_type']} {target} exists"],
            required_inputs=["finding", "owner"],
            responsible_role="approver",
            decision_points=["Is approval required?"],
            approval_points=["Approver sign-off"],
            exception_paths=["Notify owner on failure"],
            expected_output=f"{finding['kind']} resolved",
            success_metric=f"{finding['kind']} cleared within SLA",
            linked_objects=[f"{finding['target_type']}:{target}"],
            draft_runtime_targets=[runtime],  # type: ignore[list-item]
        )

    def _build_sop(self, spec_id: str, finding: dict) -> SOP:
        target = finding.get("target_id", "unknown")
        steps = [
            SOPStep(
                step_number=1, actor="system", instruction=f"Detect {finding['kind']}",
                input="ontology snapshot", output="finding",
            ),
            SOPStep(
                step_number=2, actor="approver", instruction="Review and approve",
                input="finding", output="approval", approval_required=True,
                fallback_if_failed="escalate",
            ),
            SOPStep(
                step_number=3, actor="system", instruction=f"Resolve {target}",
                input="approval", output="resolved state",
            ),
        ]
        return SOP(
            sop_id=f"sop-{spec_id}",
            title=f"SOP for {finding['kind']}",
            business_goal=f"Address {finding['kind']} on {target}",
            trigger=f"{finding['kind']} detected",
            required_inputs=["finding"],
            steps=[s.model_dump() for s in steps],
            decision_points=["approve?"],
            approval_points=["approver"],
            exception_paths=["escalate"],
            completion_criteria=f"{finding['kind']} resolved",
            owner_role="approver",
            reporting_output="truth report",
            linked_objects=[f"{finding['target_type']}:{target}"],
        )

    def _build_steps(self, finding: dict) -> list[dict]:
        return [
            {"name": "detect", "type": "trigger"},
            {"name": "review", "type": "approval"},
            {"name": "act", "type": "action"},
        ]

    def _side_effects(self, finding: dict) -> list[dict]:
        if finding["kind"] in ("overdue_money_event", "unacted_message"):
            return [{"type": "notification", "channel": "email"}]
        return [{"type": "state_change", "target": finding.get("target_id")}]
