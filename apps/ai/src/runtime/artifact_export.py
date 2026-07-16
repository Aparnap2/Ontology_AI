"""OntologyAI V5.1 — Artifact export generators + persistence (PRD §19.3, §22.6).

Generates the 6 PRD §19.3 handoff artifacts as JSON-able dicts:

* ``truth_map``
* ``ontology_snapshot``
* ``workflow_pack``
* ``sop_pack``
* ``action_register``
* ``executable_workflow_draft``

and persists any artifact to the ``artifact_exports`` table via the EXISTING
asyncpg client pattern (``asyncpg.connect(DATABASE_URL)`` — same as
``src/session/mission_state.py``). No new connection manager is introduced.

Determinism
-----------
Generators never emit random identifiers; artifact ids are produced only by
``persist_artifact`` at write time (a real DB-generated UUID), keeping the
in-memory generator output fully deterministic and testable.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import asyncpg

from src.config.database import get_database_url
from src.ontology.workflow_drafts import ExecutableWorkflowDraft

log = logging.getLogger(__name__)

# Reuse the established asyncpg DSN pattern (mirrors src/session/mission_state.py).
DATABASE_URL = get_database_url("iterateswarm")

# The 6 PRD §19.3 artifact types.
ARTIFACT_TYPES = (
    "truth_map",
    "ontology_snapshot",
    "workflow_pack",
    "sop_pack",
    "action_register",
    "executable_workflow_draft",
)


# ── Generators (deterministic, JSON-able dicts) ─────────────────────────────
def generate_truth_map(
    engagement_id: str,
    findings: list[dict[str, Any]],
    *,
    tenant_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build a truth map artifact (PRD §19.3)."""
    return {
        "artifact_type": "truth_map",
        "engagement_id": engagement_id,
        "tenant_id": tenant_id,
        "findings": list(findings),
        "generated_at": None,
    }


def generate_ontology_snapshot(
    engagement_id: str,
    objects: dict[str, list[dict[str, Any]]],
    links: list[dict[str, Any]],
    *,
    tenant_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build an ontology snapshot artifact (PRD §19.3)."""
    return {
        "artifact_type": "ontology_snapshot",
        "engagement_id": engagement_id,
        "tenant_id": tenant_id,
        "objects": objects,
        "links": list(links),
        "generated_at": None,
    }


def generate_workflow_pack(
    engagement_id: str,
    specs: list[dict[str, Any]],
    *,
    tenant_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build a workflow pack artifact (PRD §19.3)."""
    return {
        "artifact_type": "workflow_pack",
        "engagement_id": engagement_id,
        "tenant_id": tenant_id,
        "specs": list(specs),
        "generated_at": None,
    }


def generate_sop_pack(
    engagement_id: str,
    sops: list[dict[str, Any]],
    *,
    tenant_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build an SOP pack artifact (PRD §19.3)."""
    return {
        "artifact_type": "sop_pack",
        "engagement_id": engagement_id,
        "tenant_id": tenant_id,
        "sops": list(sops),
        "generated_at": None,
    }


def generate_action_register(
    engagement_id: str,
    actions: list[dict[str, Any]],
    *,
    tenant_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build an action register artifact (PRD §19.3)."""
    return {
        "artifact_type": "action_register",
        "engagement_id": engagement_id,
        "tenant_id": tenant_id,
        "actions": list(actions),
        "generated_at": None,
    }


def generate_executable_workflow_draft(
    engagement_id: str,
    draft: ExecutableWorkflowDraft,
    *,
    tenant_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build an executable workflow draft artifact (PRD §19.3)."""
    return {
        "artifact_type": "executable_workflow_draft",
        "engagement_id": engagement_id,
        "tenant_id": tenant_id,
        "draft": draft.model_dump(mode="json"),
        "generated_at": None,
    }


# ── Persistence (reuses existing asyncpg client pattern) ────────────────────
async def persist_artifact(
    tenant_id: str,
    engagement_id: str,
    artifact_type: str,
    content: dict[str, Any],
) -> Optional[str]:
    """Persist an artifact to the ``artifact_exports`` table (PRD §22.6).

    Uses the established ``asyncpg.connect(DATABASE_URL)`` pattern — no new
    connection manager. The row id is DB-generated (UUID).

    Args:
        tenant_id: Tenant identifier.
        engagement_id: Engagement identifier.
        artifact_type: One of :data:`ARTIFACT_TYPES`.
        content: JSON-able artifact body (e.g. from a generator above).

    Returns:
        The inserted row id (UUID str), or ``None`` if the write failed.

    Raises:
        ValueError: If ``artifact_type`` is not a recognized artifact type.
    """
    if artifact_type not in ARTIFACT_TYPES:
        raise ValueError(
            f"artifact_type must be one of {ARTIFACT_TYPES}, got {artifact_type!r}"
        )

    try:
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO artifact_exports (
                    tenant_id, engagement_id, artifact_type, content, created_at
                ) VALUES ($1, $2, $3, $4, now())
                RETURNING id
                """,
                tenant_id,
                engagement_id,
                artifact_type,
                json.dumps(content),
            )
            return str(row["id"]) if row else None
        finally:
            await conn.close()
    except Exception as e:  # pragma: no cover - depends on live DB
        log.warning(f"persist_artifact failed for {artifact_type}: {e}")
        return None
