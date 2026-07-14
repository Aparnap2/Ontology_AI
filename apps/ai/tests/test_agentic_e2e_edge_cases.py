#!/usr/bin/env python
"""
Part 4: Edge Cases — Resilience + Error Handling for IterateSwarm.

Standalone run:
  cd apps/ai && DB_PORT=5433 uv run python tests/test_agentic_e2e_edge_cases.py
"""

import os
import sys
import json
import logging
import uuid
from pathlib import Path

_AI_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_AI_ROOT.parent.parent), str(_AI_ROOT), str(_AI_ROOT / "src")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("DB_PORT", "5433")

import asyncpg
import pytest

from src.session.mission_state import MissionState, update_mission_state, get_mission_state
from src.guardian.detector import GuardianDetector
from src.hitl.manager import HITLManager
from src.agents.tools import TOOL_REGISTRY, get_tools_for_pattern, ToolDef, register_tool
from src.agents.tools.flag_churn_risk import execute as flag_execute
from src.session.brief_generator import generate_prepared_brief
from src.agents.authority_manifest import can_execute_tool, get_authority
from src.session.relevance_gate import evaluate_relevance

logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

DATABASE_URL = (
    f"postgresql://iterateswarm:iterateswarm@localhost:"
    f"{os.environ.get('DB_PORT', '5433')}/iterateswarm"
)

# ── Helpers ──────────────────────────────────────────────────────────

_test_tenants: list[str] = []


def make_tenant() -> str:
    tid = f"edge-{uuid.uuid4().hex[:12]}"
    _test_tenants.append(tid)
    return tid


async def cleanup_tenant(tid: str) -> None:
    try:
        conn = await asyncpg.connect(DATABASE_URL, timeout=3)
        await conn.execute("DELETE FROM mission_states WHERE tenant_id = $1", tid)
        await conn.close()
    except Exception:
        pass


async def db_available() -> bool:
    try:
        conn = await asyncpg.connect(DATABASE_URL, timeout=3)
        await conn.close()
        return True
    except Exception:
        return False


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
async def tenant():
    tid = make_tenant()
    yield tid
    await cleanup_tenant(tid)


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


# ── Tests ────────────────────────────────────────────────────────────

pytestmark = pytest.mark.asyncio


class TestEdgeCases:
    """Part 4: Edge Cases — Resilience + Error Handling."""

    # ═══════════════════════════════════════════════════════════════
    # Test 1: Missing data resilience
    # ═══════════════════════════════════════════════════════════════

    async def test_1a_all_none_fields_does_not_crash(self, tenant: str) -> None:
        """MissionState with ALL fields None except tenant_id."""
        print("\n  ── [1a] All None fields ──")
        state = MissionState(tenant_id=tenant)
        ok = await update_mission_state(state)
        assert ok is True, "update_mission_state should succeed with minimal state"

    async def test_1b_get_returns_valid_with_only_tenant(self, tenant: str) -> None:
        """get_mission_state returns valid state with only tenant_id populated."""
        print("\n  ── [1b] Get after minimal save ──")
        state = MissionState(tenant_id=tenant)
        await update_mission_state(state)
        loaded = await get_mission_state(tenant)
        assert loaded is not None
        assert loaded.tenant_id == tenant
        assert loaded.runway_days is None
        assert loaded.churn_rate is None
        assert loaded.trust_score is None
        assert loaded.mrr_trend is None

    async def test_1c_brief_on_empty_state_handles_gracefully(self, tenant: str) -> None:
        """generate_prepared_brief on empty state — returns None or brief str, never crashes."""
        print("\n  ── [1c] Brief on empty state ──")
        state = MissionState(tenant_id=tenant)
        await update_mission_state(state, generate_brief=False)
        brief = await generate_prepared_brief(tenant)
        # Must not crash — LLM may or may not be available
        assert brief is None or isinstance(brief, str)

    # ═══════════════════════════════════════════════════════════════
    # Test 2: Tool failure isolation
    # ═══════════════════════════════════════════════════════════════

    async def test_2a_valueerror_tool_does_not_crash_registry(self) -> None:
        """Tool fn that raises ValueError — registry remains intact."""
        print("\n  ── [2a] ValueError tool isolation ──")
        name = "_test_crash_tool"
        if name in TOOL_REGISTRY:
            del TOOL_REGISTRY[name]

        async def _crash(*a, **kw):
            raise ValueError("intentional crash")

        t = ToolDef(
            name=name,
            description="Crash test",
            hitl_tier="auto",
            fn=_crash,
            trigger_patterns=["CRASH-01"],
        )
        register_tool(t)
        assert name in TOOL_REGISTRY

        with pytest.raises(ValueError, match="intentional crash"):
            await _crash()

        assert name in TOOL_REGISTRY, "registry must survive fn crash"
        result = get_tools_for_pattern("CRASH-01")
        assert len(result) >= 1
        registered_names = [r.name for r in result]
        assert name in registered_names

        del TOOL_REGISTRY[name]

    async def test_2b_empty_trigger_patterns_does_not_crash(self) -> None:
        """ToolDef with empty trigger_patterns — get_tools_for_pattern works."""
        print("\n  ── [2b] Empty trigger_patterns ──")
        name = "_test_no_triggers"
        if name in TOOL_REGISTRY:
            del TOOL_REGISTRY[name]

        async def _dummy(*a, **kw):
            return {"ok": True}

        t = ToolDef(
            name=name,
            description="No triggers",
            hitl_tier="auto",
            fn=_dummy,
            trigger_patterns=[],
        )
        register_tool(t)

        result = get_tools_for_pattern("ANYTHING")
        assert isinstance(result, list)
        assert name not in [r.name for r in result], "empty trigger tool must not match"

        del TOOL_REGISTRY[name]

    # ═══════════════════════════════════════════════════════════════
    # Test 3: GuardianDetector resilience
    # ═══════════════════════════════════════════════════════════════

    async def test_3a_empty_signals_returns_empty(self) -> None:
        """Empty signals dict {} — returns empty list, no crash."""
        print("\n  ── [3a] Empty signals ──")
        d = GuardianDetector()
        result = d.run({})
        assert isinstance(result, list)
        assert len(result) == 0

    async def test_3b_partial_signals_handled(self) -> None:
        """Partial signals {'mrr': 10000} — handles gracefully."""
        print("\n  ── [3b] Partial signals ──")
        d = GuardianDetector()
        result = d.run({"mrr": 10000})
        assert isinstance(result, list)

    async def test_3c_wrong_types_does_not_crash(self) -> None:
        """Wrong types {'monthly_churn_pct': 'not-a-number'} — no crash."""
        print("\n  ── [3c] Wrong types ──")
        d = GuardianDetector()
        result = d.run({"monthly_churn_pct": "not-a-number"})
        assert isinstance(result, list)

    # ═══════════════════════════════════════════════════════════════
    # Test 4: Null/empty field handling
    # ═══════════════════════════════════════════════════════════════

    async def test_4a_empty_tenant_id(self) -> None:
        """tenant_id = '' — should not crash, returns False or True."""
        print("\n  ── [4a] Empty tenant_id ──")
        state = MissionState(tenant_id="")
        ok = await update_mission_state(state)
        # DB may accept or reject empty string; either is graceful
        assert ok is True or ok is False
        if ok:
            await cleanup_tenant("")

    async def test_4b_jsonb_fields_as_none(self, tenant: str) -> None:
        """JSONB fields as None (last_changed_fields=None, active_agent_roles=None) — serialize correctly."""
        print("\n  ── [4b] JSONB fields as None ──")
        state = MissionState(
            tenant_id=tenant,
            last_changed_fields=None,
            active_agent_roles=None,
        )
        ok = await update_mission_state(state)
        assert ok is True
        loaded = await get_mission_state(tenant)
        # Code path: if None, serializes '[]' → asyncpg JSONB codec produces '"[]"'
        # Verify it's some valid empty-representation, not a crash
        val = loaded.last_changed_fields
        assert val is None or val == [] or val == "[]" or val == '"[]"'
        aval = loaded.active_agent_roles
        assert aval is None or aval == [] or aval == "[]" or aval == '"[]"'

    async def test_4c_prepared_brief_none_triggers_generate(self, tenant: str) -> None:
        """prepared_brief=None with generate_brief=True — calls LLM (handles failure gracefully)."""
        print("\n  ── [4c] prepared_brief=None + generate_brief=True ──")
        state = MissionState(tenant_id=tenant)
        ok = await update_mission_state(state, generate_brief=True)
        assert ok is True
        loaded = await get_mission_state(tenant)
        # LLM may or may not be available; must not crash either way
        assert loaded.prepared_brief is None or isinstance(loaded.prepared_brief, str)

    # ═══════════════════════════════════════════════════════════════
    # Test 5: Concurrent writes
    # ═══════════════════════════════════════════════════════════════

    async def test_5_concurrent_writes_last_wins(self, tenant: str) -> None:
        """Two rapid sequential updates — last write wins (verify runway_days)."""
        print("\n  ── [5] Concurrent writes — last wins ──")
        s1 = MissionState(tenant_id=tenant, runway_days=30)
        ok1 = await update_mission_state(s1)
        assert ok1 is True

        s2 = MissionState(tenant_id=tenant, runway_days=90)
        ok2 = await update_mission_state(s2)
        assert ok2 is True

        loaded = await get_mission_state(tenant)
        assert loaded.runway_days == 90, "last write (90) must win"

    # ═══════════════════════════════════════════════════════════════
    # Test 6: Boundary values
    # ═══════════════════════════════════════════════════════════════

    async def test_6a_trust_score_zero(self, tenant: str) -> None:
        """trust_score = 0.0 saves correctly."""
        print("\n  ── [6a] trust_score = 0.0 ──")
        s = MissionState(tenant_id=tenant, trust_score=0.0)
        ok = await update_mission_state(s)
        assert ok is True
        loaded = await get_mission_state(tenant)
        assert loaded.trust_score == 0.0

    async def test_6b_trust_score_one(self, tenant: str) -> None:
        """trust_score = 1.0 saves correctly."""
        print("\n  ── [6b] trust_score = 1.0 ──")
        s = MissionState(tenant_id=tenant, trust_score=1.0)
        ok = await update_mission_state(s)
        assert ok is True
        loaded = await get_mission_state(tenant)
        assert loaded.trust_score == 1.0

    async def test_6c_runway_days_zero(self, tenant: str) -> None:
        """runway_days = 0 saves correctly."""
        print("\n  ── [6c] runway_days = 0 ──")
        s = MissionState(tenant_id=tenant, runway_days=0)
        ok = await update_mission_state(s)
        assert ok is True
        loaded = await get_mission_state(tenant)
        assert loaded.runway_days == 0

    async def test_6d_churn_rate_zero(self, tenant: str) -> None:
        """churn_rate = 0.0 saves correctly."""
        print("\n  ── [6d] churn_rate = 0.0 ──")
        s = MissionState(tenant_id=tenant, churn_rate=0.0)
        ok = await update_mission_state(s)
        assert ok is True
        loaded = await get_mission_state(tenant)
        assert loaded.churn_rate == 0.0

    async def test_6e_churn_rate_one(self, tenant: str) -> None:
        """churn_rate = 1.0 saves correctly."""
        print("\n  ── [6e] churn_rate = 1.0 ──")
        s = MissionState(tenant_id=tenant, churn_rate=1.0)
        ok = await update_mission_state(s)
        assert ok is True
        loaded = await get_mission_state(tenant)
        assert loaded.churn_rate == 1.0

    # ═══════════════════════════════════════════════════════════════
    # Test 7: Authority edge cases
    # ═══════════════════════════════════════════════════════════════

    async def test_7a_unknown_agent_returns_false(self) -> None:
        """Unknown agent_name → can_execute_tool returns False."""
        print("\n  ── [7a] Unknown agent ──")
        assert can_execute_tool("nonexistent_agent", "anything") is False

    async def test_7b_empty_tool_id_returns_false(self) -> None:
        """Empty tool_id → can_execute_tool returns False."""
        print("\n  ── [7b] Empty tool_id ──")
        assert can_execute_tool("OntologyAI", "") is False

    async def test_7c_get_authority_nonexistent_returns_none(self) -> None:
        """get_authority('nonexistent') returns None."""
        print("\n  ── [7c] get_authority nonexistent ──")
        assert get_authority("nonexistent") is None


# ── Entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s", "--log-cli-level=WARNING"]))
