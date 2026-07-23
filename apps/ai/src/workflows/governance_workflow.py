"""OntologyAI V5.1 — GovernanceWorkflow (PRD §8.6 / §16.6).

Validates ``PlannedAction``s + ``ExecutableWorkflowDraft``s, enforces blast
radius via ``OBJECT_WRITE_POLICY`` / governance helpers, creates approval tasks,
and gates external side effects.

Exclusivity (PRD §10.6, §12.7, §18.3):
  * ONLY this workflow may call ``ExecutableWorkflowDraft.set_status_via_governance(...)``
    and ``set_export_payload`` (via the deterministic compiler).
  * Non-governance code paths that attempt to set governance-only statuses or
    supply export_payload directly are rejected by the model validators.

Design (thin-LLM / fat-deterministic-core, PRD §11):
  * Validation, blast-radius computation, and approval gating are deterministic.
"""
from __future__ import annotations

from typing import Any, Optional

from src.runtime.deployers import DeployerResult, deploy_custom_agent, deploy_to_n8n, deploy_to_windmill
from src.schemas.specialist_response import SpecialistResponse
from src.ontology.object_types import PlannedAction
from src.ontology.workflow_drafts import ExecutableWorkflowDraft
from src.ontology.governance import GovernanceError


_BLAST_RANK = {"low": 1, "medium": 2, "high": 3}
_GOVERNANCE_ONLY = {"activated", "exported", "executing", "completed"}


class GovernanceWorkflow:
    """Governance specialist workflow (PRD §8.6 / §16.6)."""

    def __init__(self, llm_client: Optional[Any] = None) -> None:
        self.llm_client = llm_client

    def run(
        self,
        tenant_id: str,
        engagement_id: str,
        planned_actions: Optional[list[dict]] = None,
        executable_workflow_drafts: Optional[list[dict]] = None,
    ) -> SpecialistResponse:
        """Validate actions + drafts and enforce blast-radius gating.

        Args:
            tenant_id: Tenant identifier.
            engagement_id: Engagement identifier.
            planned_actions: List of PlannedAction dicts to validate/govern.
            executable_workflow_drafts: List of ExecutableWorkflowDraft dicts.

        Returns:
            SpecialistResponse with specialist="Governance" and patches to
            ``planned_actions``, ``executable_workflow_drafts``, HITL state.
        """
        planned_actions = planned_actions or []
        executable_workflow_drafts = executable_workflow_drafts or []

        governed_actions: list[dict] = []
        governed_drafts: list[dict] = []
        unresolved: list[str] = []
        hitl_ids: list[str] = []

        for pa in planned_actions:
            governed = self._govern_action(pa, unresolved)
            governed_actions.append(governed)
            if governed.get("status") == "pending_approval":
                hitl_ids.append(governed["id"])

        for draft in executable_workflow_drafts:
            governed = self._govern_draft(draft, unresolved)
            governed_drafts.append(governed)

        patch: dict[str, Any] = {
            "planned_actions": governed_actions,
            "executable_workflow_drafts": governed_drafts,
        }
        if unresolved:
            patch["unresolved_questions"] = unresolved

        requires_hitl = bool(hitl_ids)
        summary = (
            f"Governed {len(governed_actions)} action(s) and "
            f"{len(governed_drafts)} draft(s); "
            f"{len(hitl_ids)} pending approval."
        )

        return SpecialistResponse(
            specialist="Governance",
            workflow_name="GovernanceWorkflow",
            summary=summary,
            detailed_response=summary,
            objects_read=["planned_actions", "executable_workflow_drafts"],
            objects_written=["planned_actions", "executable_workflow_drafts"],
            actions_proposed=hitl_ids,
            requires_hitl=requires_hitl,
            planned_action_id=hitl_ids[0] if hitl_ids else None,
            engagement_state_patch=patch,
            confidence=0.9,
            unresolved_questions=unresolved,
        )

    # ------------------------------------------------------------------
    # Deterministic governance of actions
    # ------------------------------------------------------------------
    def _govern_action(self, pa: dict, unresolved: list[str]) -> dict:
        # Validate schema (strict). Invalid -> raise GovernanceError.
        try:
            validated = PlannedAction(**pa)
        except Exception as exc:
            raise GovernanceError(f"Invalid PlannedAction rejected: {exc}") from exc

        blast = validated.blast_radius
        requires_approval = validated.requires_approval or _BLAST_RANK[blast] >= 2

        out = validated.model_dump()
        if requires_approval:
            # Medium/high -> pending approval + block (no execution).
            out["status"] = "pending_approval"
            out["requires_approval"] = True
        else:
            # Low + auto-allowed -> execute immediately, record audit (PRD §18.2).
            out["status"] = "completed"
            out["governance_audit"] = {
                "auto_allowed": True,
                "blast_radius": blast,
                "ruling": "auto_execute",
            }
        return out

    # ------------------------------------------------------------------
    # Deterministic governance of drafts
    # ------------------------------------------------------------------
    def _govern_draft(self, draft: dict, unresolved: list[str]) -> dict:
        try:
            validated = ExecutableWorkflowDraft(**draft)
        except Exception as exc:
            raise GovernanceError(
                f"Invalid ExecutableWorkflowDraft rejected: {exc}"
            ) from exc
        # Drafts stay in draft/validated unless Governance explicitly transitions.
        return validated.model_dump()

    # ------------------------------------------------------------------
    # Governance-exclusive setters (PRD §12.7 / §18.3)
    # ONLY callable from within GovernanceWorkflow.
    # ------------------------------------------------------------------
    def activate_draft(self, draft: ExecutableWorkflowDraft) -> None:
        """Set a draft to 'activated' — governance-exclusive."""
        draft.set_status_via_governance("activated")

    def export_draft(self, draft: ExecutableWorkflowDraft) -> None:
        """Set a draft to 'exported' — governance-exclusive."""
        draft.set_status_via_governance("exported")

    def complete_draft(self, draft: ExecutableWorkflowDraft) -> None:
        """Set a draft to 'completed' — governance-exclusive."""
        draft.set_status_via_governance("completed")

    def deploy_draft(
        self,
        draft: ExecutableWorkflowDraft,
        credentials: dict[str, Any],
    ) -> DeployerResult:
        """Deploy a governance-activated draft to the target runtime.

        This is the ONLY sanctioned path for deploying compiled workflows.
        The draft MUST be in "activated" status (set by governance).

        Args:
            draft: An ExecutableWorkflowDraft with status="activated".
            credentials: Runtime-specific credentials dict.

        Returns:
            A DeployerResult with the deployment outcome.

        Raises:
            ValueError: If the draft is not yet activated.
        """
        if draft.status != "activated":
            raise ValueError(
                f"draft '{draft.id}' has status={draft.status!r}; "
                "only 'activated' drafts may be deployed. "
                "Use GovernanceWorkflow.activate_draft() first."
            )

        runtime = draft.runtime
        payload = draft.export_payload or draft.model_dump(mode="json")

        if runtime == "n8n":
            return deploy_to_n8n(payload, credentials)
        if runtime == "windmill":
            return deploy_to_windmill(payload, credentials)
        if runtime in ("custom_agent", "adk_go", "pydantic_ai", "python_agent"):
            return deploy_custom_agent(payload, credentials)
        raise ValueError(f"Unknown runtime: {runtime}")


def set_export_payload_via_compiler(draft: ExecutableWorkflowDraft, payload: dict) -> None:
    """Set the export payload via the deterministic compiler path.

    This is the ONLY sanctioned way to populate ``export_payload`` (PRD §12.7).
    It is invoked by GovernanceWorkflow after the compiler produces the payload.
    """
    draft.set_export_payload(payload)
