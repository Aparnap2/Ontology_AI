"""OntologyAI V6 — BABOK Business Analysis Artifact base model.

Provides the shared base for all first-class BA artifacts including
stable id, lifecycle status, version, provenance, and timestamps.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class ArtifactLifecycleStatus(str, Enum):
    """Canonical lifecycle states for BA artifacts."""

    PROPOSED = "proposed"
    ANALYZED = "analyzed"
    VERIFIED = "verified"
    VALIDATED = "validated"
    APPROVED = "approved"
    IMPLEMENTED = "implemented"
    EVALUATED = "evaluated"
    ARCHIVED = "archived"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _artifact_id(prefix: str) -> str:
    """Deterministic-like id factory. In tests, override with known id."""
    from src.ontology.object_types import _next_seq

    return f"{prefix}-{_next_seq()}"


class BaseArtifact(BaseModel):
    """Shared base for all BABOK business analysis artifacts.

    Attributes:
        artifact_id: Stable unique identifier.
        version: Monotonic version number.
        status: Lifecycle status from ArtifactLifecycleStatus.
        provenance: List of source reference strings (traceability).
        created_at: ISO timestamp of creation.
        updated_at: ISO timestamp of last update.
        producer: Name of the workflow that produced this artifact.
        consumer_links: List of artifact_id values that consume this artifact.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    artifact_id: str
    version: int = Field(default=1)
    status: ArtifactLifecycleStatus = Field(default=ArtifactLifecycleStatus.PROPOSED)
    provenance: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
    producer: str = ""
    consumer_links: list[str] = Field(default_factory=list)

    def new_version(self) -> "BaseArtifact":
        """Produce a new version with incremented version, reset status, and fresh timestamp.

        The new artifact carries forward provenance, producer, and consumer_links
        from the prior version. The original artifact remains unchanged (immutable).
        """
        return self.model_copy(
            update={
                "version": self.version + 1,
                "status": ArtifactLifecycleStatus.PROPOSED,
                "updated_at": _now_iso(),
                "provenance": self.provenance + [f"v{self.version}->v{self.version + 1}"],
            }
        )

    @property
    def is_finalized(self) -> bool:
        """Return True if the artifact status is APPROVED or beyond (immutable)."""
        rank = {
            ArtifactLifecycleStatus.PROPOSED: 0,
            ArtifactLifecycleStatus.ANALYZED: 1,
            ArtifactLifecycleStatus.VERIFIED: 2,
            ArtifactLifecycleStatus.VALIDATED: 3,
            ArtifactLifecycleStatus.APPROVED: 4,
            ArtifactLifecycleStatus.IMPLEMENTED: 5,
            ArtifactLifecycleStatus.EVALUATED: 6,
            ArtifactLifecycleStatus.ARCHIVED: 7,
        }
        return rank.get(self.status, 0) >= 4
