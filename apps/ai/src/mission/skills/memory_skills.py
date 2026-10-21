"""RAG / memory skills — retrieve_memory and retrieve_evidence.

Reuse the existing memory stack (``src/memory/{spine,qdrant_ops,episodic}``)
with tenant isolation and the fallback contract: when a store is unavailable,
return empty results plus errors — never raise.
"""
from __future__ import annotations

import logging
from typing import Any

from src.memory import episodic, qdrant_ops, spine
from src.mission.skill_contracts import (
    SkillContext,
    SkillDefinition,
    SkillInput,
    SkillOutput,
)
from src.mission.skill_registry import SkillRegistry

logger = logging.getLogger(__name__)


class RetrieveMemoryInput(SkillInput):
    query: str
    top_k: int = 5
    domain: str = "general"


class RetrieveMemoryOutput(SkillOutput):
    memories: list[dict[str, Any]] = []
    layers_hit: int = 0
    errors: list[str] = []


async def retrieve_memory(
    ctx: SkillContext, inp: RetrieveMemoryInput
) -> RetrieveMemoryOutput:
    """Retrieve context across the 5-layer spine + qdrant, tenant-scoped."""
    memories: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        memory_context = await spine.load_context(
            tenant_id=inp.tenant_id, query=inp.query, domain=inp.domain
        )
        for layer in (
            memory_context.episodic,
            memory_context.semantic,
            memory_context.procedural,
            memory_context.compressed,
        ):
            if isinstance(layer, list):
                memories.extend(layer)
        errors.extend(getattr(memory_context, "errors", []) or [])
    except Exception as exc:  # noqa: BLE001 — fallback contract
        logger.warning("spine.load_context failed for tenant %s: %s", inp.tenant_id, exc)
        errors.append(f"spine: {exc}")

    try:
        qdrant_hits = qdrant_ops.query_memory(
            tenant_id=inp.tenant_id,
            query_text=inp.query,
            top_k=inp.top_k,
        )
        if isinstance(qdrant_hits, list):
            memories.extend(qdrant_hits)
    except Exception as exc:  # noqa: BLE001 — fallback contract
        logger.warning("qdrant query_memory failed for tenant %s: %s", inp.tenant_id, exc)
        errors.append(f"qdrant: {exc}")

    return RetrieveMemoryOutput(memories=memories, layers_hit=len(memories), errors=errors)


class RetrieveEvidenceInput(SkillInput):
    query: str
    top_k: int = 5
    source: str = ""


class RetrieveEvidenceOutput(SkillOutput):
    evidence_records: list[dict[str, Any]] = []
    errors: list[str] = []


async def retrieve_evidence(
    ctx: SkillContext, inp: RetrieveEvidenceInput
) -> RetrieveEvidenceOutput:
    """Search episodic memory + qdrant for evidence, tenant-scoped."""
    evidence: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        episodes = episodic.EpisodicMemory(collection="episodes")
        records = episodes.search(
            tenant_id=inp.tenant_id,
            query=inp.query,
            top_k=inp.top_k,
            event_type=inp.source or None,
        )
        if isinstance(records, list):
            evidence.extend(records)
    except Exception as exc:  # noqa: BLE001 — fallback contract
        logger.warning("episodic search failed for tenant %s: %s", inp.tenant_id, exc)
        errors.append(f"episodic: {exc}")

    try:
        qdrant_hits = qdrant_ops.search_memory(
            tenant_id=inp.tenant_id,
            query=inp.query,
            limit=inp.top_k,
        )
        if isinstance(qdrant_hits, list):
            evidence.extend(qdrant_hits)
    except Exception as exc:  # noqa: BLE001 — fallback contract
        logger.warning("qdrant search_memory failed for tenant %s: %s", inp.tenant_id, exc)
        errors.append(f"qdrant: {exc}")

    return RetrieveEvidenceOutput(evidence_records=evidence, errors=errors)


def register() -> None:
    """Register the 2 RAG / memory skills."""
    SkillRegistry.register(
        SkillDefinition(
            name="retrieve_memory",
            description="Retrieve tenant-scoped context across the memory spine.",
            input_model=RetrieveMemoryInput,
            output_model=RetrieveMemoryOutput,
            run=retrieve_memory,
            uses_llm=False,
            llm_calls=[],
            capability_ops=[],
            allowed_roles=["revops", "productops", "orgint"],
        )
    )
    SkillRegistry.register(
        SkillDefinition(
            name="retrieve_evidence",
            description="Search episodic memory and qdrant for evidence.",
            input_model=RetrieveEvidenceInput,
            output_model=RetrieveEvidenceOutput,
            run=retrieve_evidence,
            uses_llm=False,
            llm_calls=[],
            capability_ops=[],
            allowed_roles=["revops", "productops", "orgint"],
        )
    )