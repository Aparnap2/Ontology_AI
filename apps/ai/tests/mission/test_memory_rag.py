"""RAG / memory skill tests — requirement #3.

``retrieve_memory`` / ``retrieve_evidence`` reuse the existing memory stack
(``src/memory/{spine,qdrant_ops,episodic,semantic}.py``) with tenant isolation
and the fallback contract (empty results when the store is unavailable).
"""

from __future__ import annotations

import pytest

from src.memory import episodic, qdrant_ops, spine
from src.mission.skill_contracts import SkillContext
from src.mission.skills.memory_skills import (
    RetrieveEvidenceInput,
    RetrieveEvidenceOutput,
    RetrieveMemoryInput,
    RetrieveMemoryOutput,
    retrieve_evidence,
    retrieve_memory,
)


class TestRetrieveMemory:
    async def test_retrieve_memory_calls_spine_load_context(self, monkeypatch):
        """retrieve_memory drives the real 5-layer spine with the tenant's query."""
        called: dict = {}

        async def fake_load_context(tenant_id, query, domain):
            called["tenant_id"] = tenant_id
            called["query"] = query
            called["domain"] = domain
            return spine.MemoryContext(
                episodic=[{"content": "ep-1", "score": 0.9}],
                semantic=[{"fact": "sem-1"}],
            )

        monkeypatch.setattr(spine, "load_context", fake_load_context)
        monkeypatch.setattr(
            qdrant_ops,
            "query_memory",
            lambda tenant_id, query_text, memory_types=None, top_k=5, min_score=0.7, temporal_boost=True: [],
        )
        ctx = SkillContext(tenant_id="t1")
        out: RetrieveMemoryOutput = await retrieve_memory(
            ctx, RetrieveMemoryInput(tenant_id="t1", query="what did we decide?", top_k=3, domain="ops")
        )
        assert called["tenant_id"] == "t1"
        assert "decide" in called["query"]
        assert called["domain"] == "ops"
        assert len(out.memories) >= 2  # episodic + semantic from the spine

    async def test_tenant_isolation_passed(self, monkeypatch):
        """tenant_id is threaded into every memory layer call."""
        seen: list[str] = []

        async def fake_load_context(tenant_id, query, domain):
            seen.append(tenant_id)
            return spine.MemoryContext()

        monkeypatch.setattr(spine, "load_context", fake_load_context)
        monkeypatch.setattr(
            qdrant_ops,
            "query_memory",
            lambda tenant_id, query_text, memory_types=None, top_k=5, min_score=0.7, temporal_boost=True: seen.append(tenant_id) or [],
        )
        ctx = SkillContext(tenant_id="t1")
        out = await retrieve_memory(ctx, RetrieveMemoryInput(tenant_id="t1", query="q", top_k=5))
        assert seen == ["t1", "t1"]

    async def test_fallback_contract_returns_empty_on_unavailable(self, monkeypatch):
        """When every memory store is down, retrieve_memory returns empty, not an error."""

        async def boom_load_context(tenant_id, query, domain):
            raise RuntimeError("qdrant down")

        def boom_query(*args, **kwargs):
            raise RuntimeError("qdrant down")

        monkeypatch.setattr(spine, "load_context", boom_load_context)
        monkeypatch.setattr(qdrant_ops, "query_memory", boom_query)
        ctx = SkillContext(tenant_id="t1")
        out = await retrieve_memory(ctx, RetrieveMemoryInput(tenant_id="t1", query="q", top_k=3))
        assert out.memories == []
        assert out.errors


class TestRetrieveEvidence:
    async def test_retrieve_evidence_calls_episodic_search(self, monkeypatch):
        """retrieve_evidence searches episodic memory with the tenant filter."""
        called: dict = {}

        def fake_search(self, tenant_id, query, top_k=5, event_type=None):
            called["tenant_id"] = tenant_id
            called["query"] = query
            return [{"score": 0.9, "content": "evidence-1"}]

        monkeypatch.setattr(episodic.EpisodicMemory, "search", fake_search)
        monkeypatch.setattr(
            qdrant_ops,
            "search_memory",
            lambda tenant_id, query, memory_type=None, limit=5: [],
        )
        ctx = SkillContext(tenant_id="t1")
        out: RetrieveEvidenceOutput = await retrieve_evidence(
            ctx, RetrieveEvidenceInput(tenant_id="t1", query="blocker", source="jira", top_k=5)
        )
        assert called["tenant_id"] == "t1"
        assert "blocker" in called["query"]
        assert out.evidence_records == [{"score": 0.9, "content": "evidence-1"}]

    async def test_fallback_contract_returns_empty_on_unavailable(self, monkeypatch):
        """Episodic/qdrant outages yield empty evidence, not exceptions."""

        def boom_search(self, *args, **kwargs):
            raise RuntimeError("episodes down")

        def boom_qdrant(*args, **kwargs):
            raise RuntimeError("qdrant down")

        monkeypatch.setattr(episodic.EpisodicMemory, "search", boom_search)
        monkeypatch.setattr(qdrant_ops, "search_memory", boom_qdrant)
        ctx = SkillContext(tenant_id="t1")
        out = await retrieve_evidence(ctx, RetrieveEvidenceInput(tenant_id="t1", query="q", source="slack"))
        assert out.evidence_records == []
        assert out.errors