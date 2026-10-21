"""Deterministic context checkpoint schema (issue #63, Sprint 1).

Evidence objects in, checkpoint out. No LLM calls, no connector imports.
Reuses frozen ``Evidence`` type (+ compat ``Onboarding`` alias) — never redefines them.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class RelevantEvidence(BaseModel):
    """One attributed evidence citation inside a checkpoint."""

    model_config = ConfigDict(extra="forbid", strict=True)

    evidence_id: str
    source: str
    freshness: Literal["fresh", "stale"]
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: str
    excerpt: str


class ContextCheckpoint(BaseModel):
    """Assembled deterministic context for one mission trigger event."""

    model_config = ConfigDict(extra="forbid", strict=True)

    checkpoint_id: str
    tenant_id: str
    mission_id: str
    trigger_event_id: str
    version: int = 1
    affected_entities: list[str] = Field(default_factory=list)
    current_state: str = "unknown"
    state_delta: dict[str, str] = Field(default_factory=dict)
    relevant_evidence: list[RelevantEvidence] = Field(default_factory=list)
    relevant_process: Optional[str] = None
    relevant_sop: Optional[str] = None
    applicable_policies: list[str] = Field(default_factory=list)
    kpi_snapshot: dict[str, float] = Field(default_factory=dict)
    recent_actions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    allowed_capabilities: list[str] = Field(default_factory=list)
    authority_constraints: list[str] = Field(default_factory=list)
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    provenance: str
