"""OntologyAI V5.1 — Executable Workflow Draft (PRD §12.7).

SINGLE SOURCE OF TRUTH for :class:`ExecutableWorkflowDraft`. Re-exported by
``src.schemas.executable_workflow_draft``.

Hard rules (PRD §12.7, §10.6, §18.3)
-------------------------------------
* ``export_payload`` may ONLY be populated by deterministic compiler logic
  (``runtime/n8n_compiler.py`` / ``runtime/custom_agent_compiler.py``). The
  LLM path may propose structure but must never write ``export_payload``.
* ``status="activated"`` may ONLY be set by ``GovernanceWorkflow``. No other
  workflow may transition a draft into ``activated`` / ``exported`` /
  ``executing`` / ``completed``.

These rules are enforced by model validators + guarded setters so they hold
regardless of where the object is constructed.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator

# Statuses that only GovernanceWorkflow may set (PRD §18.3).
_GOVERNANCE_ONLY_STATUSES = {"activated", "exported", "executing", "completed"}


class ExecutableWorkflowDraft(BaseModel):
    """A machine-readable workflow draft ready for compilation or export."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    runtime: Literal["n8n", "custom_agent", "windmill"]
    name: str
    source_workflow_spec_id: str
    status: Literal[
        "draft",
        "validated",
        "pending_approval",
        "approved",
        "exported",
        "activated",
        "failed",
    ] = "draft"
    trigger: dict = {}
    inputs: list[dict] = []
    steps: list[dict] = []
    decision_points: list[dict] = []
    approvals: list[dict] = []
    side_effects: list[dict] = []
    fallback_paths: list[dict] = []
    success_criteria: list[str] = []
    export_payload: Optional[dict] = None
    source_refs: list[str] = []

    # ── Internal bookkeeping (not part of the public contract) ──────────
    # Tracks whether export_payload / governance status were set via the
    # sanctioned code paths. Set True only by the compiler / governance.
    _export_payload_set_by_compiler: bool = False
    _status_set_by_governance: bool = False

    # ------------------------------------------------------------------
    # Rule 1: export_payload only via compiler
    # ------------------------------------------------------------------
    @model_validator(mode="after")
    def _guard_export_payload(self) -> "ExecutableWorkflowDraft":
        if self.export_payload is not None and not self._export_payload_set_by_compiler:
            # A draft constructed with an export_payload outside the compiler
            # is rejected — the payload must be produced deterministically.
            raise ValueError(
                "export_payload may only be set by the deterministic compiler, "
                "not supplied directly."
            )
        return self

    # ------------------------------------------------------------------
    # Rule 2: status in governance-only set only via GovernanceWorkflow
    # ------------------------------------------------------------------
    @model_validator(mode="after")
    def _guard_governance_status(self) -> "ExecutableWorkflowDraft":
        if self.status in _GOVERNANCE_ONLY_STATUSES and not self._status_set_by_governance:
            raise ValueError(
                f"status={self.status!r} may only be set by GovernanceWorkflow."
            )
        return self

    # ------------------------------------------------------------------
    # Sanctioned setters (used by compiler / governance only)
    # ------------------------------------------------------------------
    def set_export_payload(self, payload: dict) -> None:
        """Set the export payload — ONLY callable by the deterministic compiler."""
        object.__setattr__(self, "export_payload", payload)
        object.__setattr__(self, "_export_payload_set_by_compiler", True)

    def set_status_via_governance(self, status: str) -> None:
        """Set a governance-only status — ONLY callable by GovernanceWorkflow."""
        if status not in _GOVERNANCE_ONLY_STATUSES:
            raise ValueError(f"status={status!r} is not a governance-only status")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "_status_set_by_governance", True)

    @classmethod
    def governance_only_statuses(cls) -> set[str]:
        """Expose the set of statuses reserved for GovernanceWorkflow."""
        return set(_GOVERNANCE_ONLY_STATUSES)
