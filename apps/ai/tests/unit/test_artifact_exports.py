"""TDD tests for artifact export generators + persistence (PRD §19.3, §22.6).

Written BEFORE implementation. Run first — must FAIL, then implement to pass.

The 6 PRD §19.3 artifacts each have a generator returning a JSON-able dict:
* truth_map
* ontology_snapshot
* workflow_pack
* sop_pack
* action_register
* executable_workflow_draft

``persist_artifact`` writes a row to the ``artifact_exports`` table via the
existing asyncpg client. The DB-backed test is skipped when no live Postgres
is reachable (mirrors the repo's established skip guard).
"""
from __future__ import annotations

import asyncio
import os

import asyncpg
import pytest

from src.runtime import artifact_export
from src.ontology.workflow_drafts import ExecutableWorkflowDraft


# ── DB availability guard (mirrors tests/integration/test_mission_state.py) ──
def _db_available() -> bool:
    url = os.environ.get("DATABASE_URL")
    if not url:
        return False
    try:
        asyncio.run(asyncpg.connect(url, timeout=3))
    except Exception:
        return False
    return True


requires_db = pytest.mark.skipif(not _db_available(), reason="No live Postgres available")


class TestArtifactGeneratorsShape:
    """Each generator returns the right shape."""

    def test_truth_map_shape(self):
        out = artifact_export.generate_truth_map(
            engagement_id="eng-1",
            findings=[{"id": "t1", "kind": "stuck", "summary": "blocked"}],
        )
        assert out["artifact_type"] == "truth_map"
        assert out["engagement_id"] == "eng-1"
        assert isinstance(out["findings"], list)

    def test_ontology_snapshot_shape(self):
        out = artifact_export.generate_ontology_snapshot(
            engagement_id="eng-1",
            objects={"Party": [{"id": "p1"}]},
            links=[{"name": "party_engagement"}],
        )
        assert out["artifact_type"] == "ontology_snapshot"
        assert "objects" in out and "links" in out

    def test_workflow_pack_shape(self):
        out = artifact_export.generate_workflow_pack(
            engagement_id="eng-1",
            specs=[{"workflow_spec_id": "ws-1", "workflow_name": "W"}],
        )
        assert out["artifact_type"] == "workflow_pack"
        assert isinstance(out["specs"], list)

    def test_sop_pack_shape(self):
        out = artifact_export.generate_sop_pack(
            engagement_id="eng-1",
            sops=[{"sop_id": "sop-1", "title": "S"}],
        )
        assert out["artifact_type"] == "sop_pack"
        assert isinstance(out["sops"], list)

    def test_action_register_shape(self):
        out = artifact_export.generate_action_register(
            engagement_id="eng-1",
            actions=[{"id": "a1", "type": "create", "status": "draft"}],
        )
        assert out["artifact_type"] == "action_register"
        assert isinstance(out["actions"], list)

    def test_executable_workflow_draft_shape(self):
        draft = ExecutableWorkflowDraft(
            id="draft-1",
            runtime="n8n",
            name="D",
            source_workflow_spec_id="ws-1",
        )
        out = artifact_export.generate_executable_workflow_draft(
            engagement_id="eng-1", draft=draft
        )
        assert out["artifact_type"] == "executable_workflow_draft"
        assert out["draft"]["id"] == "draft-1"


class TestArtifactGeneratorsDeterminism:
    """Generators are deterministic (no random ids)."""

    def test_truth_map_deterministic(self):
        import json

        a = artifact_export.generate_truth_map("eng-1", [{"id": "t1"}])
        b = artifact_export.generate_truth_map("eng-1", [{"id": "t1"}])
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


class TestPersistArtifact:
    """persist_artifact writes a row to artifact_exports."""

    @requires_db
    async def test_persist_writes_row(self):
        tenant_id = "tenant-test"
        engagement_id = "eng-persist"
        content = artifact_export.generate_truth_map(
            engagement_id, [{"id": "t1", "kind": "stuck"}]
        )
        record_id = await artifact_export.persist_artifact(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            artifact_type="truth_map",
            content=content,
        )
        assert record_id is not None
        # Verify the row exists.
        url = os.environ["DATABASE_URL"]
        conn = await asyncpg.connect(url, timeout=3)
        try:
            row = await conn.fetchrow(
                "SELECT artifact_type, content FROM artifact_exports WHERE id = $1",
                record_id,
            )
            assert row is not None
            assert row["artifact_type"] == "truth_map"
        finally:
            await conn.close()
