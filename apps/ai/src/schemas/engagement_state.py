"""OntologyAI V5.1 — Canonical EngagementState (PRD §14.1 / §14.2).

``EngagementState`` is the single shared state shape that every specialist
workflow reads and writes back to via typed patches (never arbitrary freeform
state). The ``merge_patch`` helper performs a deterministic, provenance-
preserving merge of a partial patch into a base state and rejects unknown keys.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, ValidationError

# Allowed top-level patch keys (PRD §14.1). Unknown keys are rejected.
_ALLOWED_PATCH_KEYS = {
    "operator_goal",
    "discovery_notes",
    "ontology_objects",
    "ontology_links",
    "truth_findings",
    "workflow_specs",
    "executable_workflow_drafts",
    "planned_actions",
    "unresolved_questions",
    "data_sources",
    "freshness",
    "phase",
    # BABOK strategy artifacts (V5.1 extension)
    "current_state_descriptions",
    "business_objectives",
    "risk_analyses",
    "change_strategies",
    "solution_evaluations",
    # Agent mesh: peer-to-peer message inbox
    "agent_inbox",
    # Immutable after creation, but listed so the explicit check fires
    "workspace_mode",
}

# BABOK artifact list field names that require finalized-artifact protection.
_BABOK_ARTIFACT_PATCH_KEYS = {
    "current_state_descriptions",
    "business_objectives",
    "risk_analyses",
    "change_strategies",
    "solution_evaluations",
}

# Rank mapping for artifact lifecycle status to determine finalization.
_ARTIFACT_STATUS_RANK = {
    "proposed": 0,
    "analyzed": 1,
    "verified": 2,
    "validated": 3,
    "approved": 4,
    "implemented": 5,
    "evaluated": 6,
    "archived": 7,
}

PHASES = Literal[
    "discovery",
    "ontology_mapping",
    "truth_analysis",
    "workflow_design",
    "governance_review",
    "deployment_planning",
    "handoff",
]

WORKSPACE_MODES = Literal["dashboard", "workspace", "fde_assisted"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EngagementState(BaseModel):
    """Canonical shared state for an engagement workspace (PRD §14.1)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    engagement_id: str
    tenant_id: str
    workspace_mode: WORKSPACE_MODES
    phase: PHASES
    operator_goal: Optional[str] = None
    discovery_notes: list[dict] = []
    ontology_objects: dict[str, list[dict]] = {}
    ontology_links: list[dict] = []
    truth_findings: list[dict] = []
    workflow_specs: list[dict] = []
    executable_workflow_drafts: list[dict] = []
    planned_actions: list[dict] = []
    unresolved_questions: list[str] = []
    data_sources: list[dict] = []
    freshness: dict[str, str] = {}
    updated_at: str = ""
    # BABOK strategy artifacts (V5.1 extension)
    current_state_descriptions: list[dict] = []
    business_objectives: list[dict] = []
    risk_analyses: list[dict] = []
    change_strategies: list[dict] = []
    solution_evaluations: list[dict] = []
    # Agent mesh: peer-to-peer message inbox
    agent_inbox: list[dict] = []

    # ── workspace_mode is immutable after creation (PRD §14.2) ──────────
    def model_post_init(self, __context) -> None:
        if not self.updated_at:
            object.__setattr__(self, "updated_at", _now_iso())

    # ------------------------------------------------------------------
    # Deterministic, provenance-preserving patch merge (PRD §14.2)
    # ------------------------------------------------------------------
    def merge_patch(self, patch: dict, provenance: Optional[str] = None) -> "EngagementState":
        """Return a NEW EngagementState with ``patch`` merged in deterministically.

        Rules:
        * Unknown top-level keys are rejected (``ValueError``).
        * ``workspace_mode`` is immutable — cannot be patched after creation.
        * List-valued fields are appended (deterministic order preserved).
        * Dict-valued fields are deep-merged (patch wins on key conflicts).
        * ``updated_at`` is refreshed; ``freshness`` records the provenance of
          the merge.
        * The base state is never mutated (returns a copy).
        """
        if not isinstance(patch, dict):
            raise ValueError("patch must be a dict")

        unknown = set(patch.keys()) - _ALLOWED_PATCH_KEYS
        if unknown:
            raise ValueError(f"Unknown patch keys rejected: {sorted(unknown)}")

        if "workspace_mode" in patch:
            raise ValueError("workspace_mode is immutable and cannot be patched")

        merged = self.model_dump()
        for key, value in patch.items():
            if key == "phase":
                merged["phase"] = value
                continue
            current = merged.get(key)
            if isinstance(current, list) and isinstance(value, list):
                # BABOK artifact protection: refuse append if finalized artifact exists.
                if key in _BABOK_ARTIFACT_PATCH_KEYS:
                    for entry in current:
                        if isinstance(entry, dict):
                            entry_status = entry.get("status", "proposed")
                            if _ARTIFACT_STATUS_RANK.get(entry_status, 0) >= 4:
                                raise ValueError(
                                    f"Cannot patch '{key}': finalized artifact(s) exist. "
                                    f"Use add_artifact_version() to create a new version instead."
                                )
                merged[key] = current + value
            elif isinstance(current, dict) and isinstance(value, dict):
                merged[key] = _deep_merge(current, value)
            else:
                merged[key] = copy.deepcopy(value)

        merged["updated_at"] = _now_iso()
        if provenance:
            fresh = dict(merged.get("freshness", {}))
            fresh[provenance] = _now_iso()
            merged["freshness"] = fresh

        return EngagementState(**merged)

    def add_artifact_version(
        self, field: str, new_artifact: dict
    ) -> "EngagementState":
        """Replace an existing finalized artifact with a newer version.

        Args:
            field: BABOK artifact list field name (must be in
                   ``_BABOK_ARTIFACT_PATCH_KEYS``).
            new_artifact: The replacement artifact dict. Must have the same
                          ``artifact_id`` as the existing finalized entry.

        Returns:
            A new ``EngagementState`` with the artifact replaced.

        Raises:
            ValueError: If the field is not recognized, no matching artifact
                        is found, or the existing artifact is not finalized.
        """
        if field not in _BABOK_ARTIFACT_PATCH_KEYS:
            raise ValueError(
                f"Field '{field}' is not a BABOK artifact list. "
                f"Valid: {sorted(_BABOK_ARTIFACT_PATCH_KEYS)}"
            )

        existing_list = list(getattr(self, field, []))
        new_id = new_artifact.get("artifact_id", "")
        target_idx: int | None = None

        for i, entry in enumerate(existing_list):
            if isinstance(entry, dict) and entry.get("artifact_id") == new_id:
                target_idx = i
                break

        if target_idx is None:
            raise ValueError(
                f"No existing artifact with artifact_id '{new_id}' in '{field}'"
            )

        old_status = existing_list[target_idx].get("status", "proposed")
        if _ARTIFACT_STATUS_RANK.get(old_status, 0) < 4:
            raise ValueError(
                f"Existing artifact '{new_id}' in '{field}' has status "
                f"'{old_status}' — not finalized. Cannot version-replace."
            )

        new_list = list(existing_list)
        new_list[target_idx] = new_artifact

        return self.model_copy(
            update={
                field: new_list,
                "updated_at": _now_iso(),
            }
        )

    @classmethod
    def create(
        cls,
        engagement_id: str,
        tenant_id: str,
        workspace_mode: str,
        operator_goal: Optional[str] = None,
    ) -> "EngagementState":
        """Create a fresh EngagementState initialized in the discovery phase."""
        return cls(
            engagement_id=engagement_id,
            tenant_id=tenant_id,
            workspace_mode=workspace_mode,  # type: ignore[arg-type]
            phase="discovery",
            operator_goal=operator_goal,
            updated_at=_now_iso(),
        )


def _deep_merge(base: dict, patch: dict) -> dict:
    """Deterministic deep merge; patch values win on scalar/key conflicts."""
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def merge_patch(base: "EngagementState", patch: dict, provenance: Optional[str] = None) -> "EngagementState":
    """Module-level deterministic merge helper (PRD §14.2).

    Rejects unknown keys and preserves provenance. Delegates to
    :meth:`EngagementState.merge_patch`.
    """
    if not isinstance(base, EngagementState):
        raise TypeError("base must be an EngagementState")
    try:
        return base.merge_patch(patch, provenance=provenance)
    except ValidationError as exc:
        raise ValueError(f"Patch produced an invalid EngagementState: {exc}") from exc
