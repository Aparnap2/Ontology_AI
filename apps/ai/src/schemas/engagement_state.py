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

WORKSPACE_MODES = Literal["fde_assisted", "client_self_serve"]


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
