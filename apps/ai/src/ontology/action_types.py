"""OntologyAI V5.1 — Action types and registry (PRD §12.6).

``PlannedAction`` is the canonical governed-action model. It is defined in
``src.ontology.object_types`` (the single source of truth for object types)
and re-exported here so callers may import it from either location.

This module also provides a small ``ActionRegistry`` helper used by the
WorkflowBuilder and Governance workflows to mint deterministic ``PlannedAction``
records without an LLM in the loop.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict

from src.ontology.object_types import PlannedAction

# Re-export the canonical model so `from src.ontology.action_types import
# PlannedAction` works (and legacy governance.py import path is preserved).
__all__ = ["PlannedAction", "ActionRegistry", "ActionRegistryEntry"]


class ActionRegistryEntry(BaseModel):
    """A registered action type with its default blast-radius policy."""

    model_config = ConfigDict(extra="forbid", strict=True)

    type: str
    title_template: str
    default_blast_radius: str
    requires_approval: bool


# Default registry of known action types. Medium/high blast radius and any
# external-side-effect action requires approval (PRD §10.7 / §18.1).
ACTION_REGISTRY: dict[str, ActionRegistryEntry] = {
    "create_note": ActionRegistryEntry(
        type="create_note",
        title_template="Add internal note to {target_id}",
        default_blast_radius="low",
        requires_approval=False,
    ),
    "tag_needs_review": ActionRegistryEntry(
        type="tag_needs_review",
        title_template="Flag {target_id} as needs review",
        default_blast_radius="low",
        requires_approval=False,
    ),
    "create_draft_spec": ActionRegistryEntry(
        type="create_draft_spec",
        title_template="Draft workflow spec for {target_id}",
        default_blast_radius="low",
        requires_approval=False,
    ),
    "create_draft_message": ActionRegistryEntry(
        type="create_draft_message",
        title_template="Draft message for {target_id}",
        default_blast_radius="low",
        requires_approval=False,
    ),
    "create_draft_action": ActionRegistryEntry(
        type="create_draft_action",
        title_template="Draft planned action for {target_id}",
        default_blast_radius="low",
        requires_approval=False,
    ),
    "create_draft_workflow": ActionRegistryEntry(
        type="create_draft_workflow",
        title_template="Draft executable workflow for {target_id}",
        default_blast_radius="low",
        requires_approval=False,
    ),
    "export_artifact": ActionRegistryEntry(
        type="export_artifact",
        title_template="Export artifact for {target_id}",
        default_blast_radius="low",
        requires_approval=False,
    ),
    "change_ownership": ActionRegistryEntry(
        type="change_ownership",
        title_template="Change owner of {target_id}",
        default_blast_radius="medium",
        requires_approval=True,
    ),
    "send_communication": ActionRegistryEntry(
        type="send_communication",
        title_template="Send communication to {target_id}",
        default_blast_radius="high",
        requires_approval=True,
    ),
    "money_state_change": ActionRegistryEntry(
        type="money_state_change",
        title_template="Change money state of {target_id}",
        default_blast_radius="high",
        requires_approval=True,
    ),
    "close_issue": ActionRegistryEntry(
        type="close_issue",
        title_template="Close issue {target_id}",
        default_blast_radius="medium",
        requires_approval=True,
    ),
    "activate_workflow": ActionRegistryEntry(
        type="activate_workflow",
        title_template="Activate workflow {target_id}",
        default_blast_radius="high",
        requires_approval=True,
    ),
    # BABOK strategy artifact actions (V5.1 extension)
    "generate_current_state": ActionRegistryEntry(
        type="generate_current_state",
        title_template="Generate current state description for {target_id}",
        default_blast_radius="low",
        requires_approval=False,
    ),
    "generate_objectives": ActionRegistryEntry(
        type="generate_objectives",
        title_template="Generate business objectives for {target_id}",
        default_blast_radius="low",
        requires_approval=False,
    ),
    "generate_risk_analysis": ActionRegistryEntry(
        type="generate_risk_analysis",
        title_template="Generate risk analysis for {target_id}",
        default_blast_radius="low",
        requires_approval=False,
    ),
    "generate_change_strategy": ActionRegistryEntry(
        type="generate_change_strategy",
        title_template="Generate change strategy for {target_id}",
        default_blast_radius="medium",
        requires_approval=True,
    ),
    "record_evaluation": ActionRegistryEntry(
        type="record_evaluation",
        title_template="Record solution evaluation for {target_id}",
        default_blast_radius="low",
        requires_approval=False,
    ),
}


class ActionRegistry:
    """Helper for minting deterministic ``PlannedAction`` records."""

    @staticmethod
    def create(
        action_type: str,
        target_object_type: str,
        target_id: str,
        requested_by: str,
        rationale: str,
        *,  # require keyword args below
        title: Optional[str] = None,
        blast_radius: Optional[str] = None,
        requires_approval: Optional[bool] = None,
        status: str = "draft",
        source_refs: Optional[list[str]] = None,
        action_id: Optional[str] = None,
    ) -> PlannedAction:
        """Create a ``PlannedAction`` from a registered action type.

        Blast radius / requires_approval default from the registry entry but
        may be overridden. This is deterministic code (no LLM).
        """
        entry = ACTION_REGISTRY.get(action_type)
        if entry is None:
            # Unknown action types default to high blast radius + approval.
            eff_blast = blast_radius or "high"
            eff_requires = (
                requires_approval if requires_approval is not None else True
            )
            eff_title = title or f"Action {action_type} on {target_id}"
        else:
            eff_blast = blast_radius or entry.default_blast_radius
            eff_requires = (
                requires_approval
                if requires_approval is not None
                else entry.requires_approval
            )
            eff_title = title or entry.title_template.format(target_id=target_id)

        return PlannedAction(
            id=action_id or f"pa-{action_type}-{target_id}",
            type=action_type,
            title=eff_title,
            blast_radius=eff_blast,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            requested_by=requested_by,
            target_object_type=target_object_type,  # type: ignore[arg-type]
            target_id=target_id,
            rationale=rationale,
            requires_approval=eff_requires,
            source_refs=source_refs or [],
        )
