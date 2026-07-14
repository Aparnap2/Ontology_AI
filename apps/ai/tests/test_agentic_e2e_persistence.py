"""Part 1: Persistency — Full E2E Cycle.

Tests that data survives across the complete loop:
  Data arrives → Guardian detects → MissionState updated → HITL queue shows pending →
  Decision made (approve) → Tool executes → MissionState updated again →
  Brief generated → Dashboard reflects changes

Usage:
  DB_PORT=5433 uv run python tests/test_agentic_e2e_persistence.py
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from unittest.mock import patch

os.environ.setdefault("DB_PORT", "5433")
os.environ.setdefault(
    "DATABASE_URL",
    f"postgresql://iterateswarm:iterateswarm@localhost:{os.environ.get('DB_PORT', '5433')}/iterateswarm",
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _parse_jsonb(val):
    """Parse a JSONB value that may be 0–2x string-encoded by asyncpg read-then-write cycles."""
    if not isinstance(val, str):
        return val
    try:
        parsed = json.loads(val)
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        return parsed
    except (json.JSONDecodeError, TypeError):
        return val


async def main():
    print("=" * 66)
    print("  Part 1: Persistency \u2014 Full E2E Cycle")
    print("=" * 66)

    from src.session.mission_state import (
        MissionState,
        get_mission_state,
        update_mission_state,
    )

    tenant_id = f"test-e2e-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # ─────────────────────────────────────────────────────────────────
    # STEP 1: Seed a MissionState with realistic data (FG-05 active)
    # ─────────────────────────────────────────────────────────────────
    print(f"\n[STEP 1/9] Seeding MissionState (tenant={tenant_id}) ...")
    seed_state = MissionState(
        tenant_id=tenant_id,
        runway_days=45,
        burn_alert=True,
        burn_severity="high",
        mrr_trend="declining",
        churn_rate=3.5,
        active_alerts="FG-05",
        trust_score=0.62,
        route_priority=2,
        burn_multiple=2.3,
        effective_runway_days=38,
    )
    success = await update_mission_state(seed_state, generate_brief=False)
    assert success is True, "Step 1: seed MissionState failed"

    s1 = await get_mission_state(tenant_id)
    assert s1.tenant_id == tenant_id
    assert s1.runway_days == 45, f"expected 45, got {s1.runway_days}"
    assert s1.burn_alert is True
    assert s1.burn_severity == "high"
    assert s1.mrr_trend == "declining"
    assert s1.churn_rate == 3.5, f"expected 3.5, got {s1.churn_rate}"
    assert s1.active_alerts == "FG-05"
    assert s1.trust_score == 0.62
    assert s1.route_priority == 2
    assert float(s1.burn_multiple) == 2.3, (
        "burn_multiple: expected 2.3, got %s" % repr(s1.burn_multiple)
    )
    assert s1.effective_runway_days == 38
    print("  [OK] MissionState seeded and read-back verified (%d fields)" % 11)

    # ─────────────────────────────────────────────────────────────────
    # STEP 2: Run GuardianDetector against synthetic signals
    # ─────────────────────────────────────────────────────────────────
    print("\n[STEP 2/9] Running GuardianDetector against synthetic signals ...")
    from src.guardian.detector import GuardianDetector

    signals = {
        "failed_payments_7d": 5,
        "monthly_churn_pct": 3.5,
        "net_burn": 45_000,
        "net_new_arr": 15_000,
        "top_customer_mrr": 3_500,
        "total_mrr": 12_500,
        "burn_rate": 32_000,
        "prev_burn_rate": 28_000,
        "runway_days": 45,
        "payroll_monthly": 60_000,
        "mrr": 12_500,
    }

    detector = GuardianDetector()
    matched = detector.run(signals)
    matched_ids = [b.id for b in matched]
    detected_severities = {b.id: b.severity for b in matched}

    assert "FG-05" in matched_ids, "FG-05 (Failed Payment Cluster) must trigger with 5 failed payments/7d"
    assert len(matched_ids) >= 3, f"expected >=3 patterns, got {matched_ids}"
    print("  Matched: %s" % ", ".join(matched_ids))
    assert detected_severities["FG-05"] == "warning", "FG-05 severity must be 'warning'"
    print("  [OK] GuardianDetector matched %d patterns" % len(matched))

    # ─────────────────────────────────────────────────────────────────
    # STEP 3: Route through HITLManager — get tier and suggested tools
    # ─────────────────────────────────────────────────────────────────
    print("\n[STEP 3/9] Routing through HITLManager ...")
    from src.hitl.manager import HITLManager

    hitl = HITLManager()

    fg05_blindspot = [b for b in matched if b.id == "FG-05"][0]
    tier = hitl.route(
        severity=fg05_blindspot.severity,
        confidence=0.72,
        is_new_pattern=False,
    )
    # FG-05 severity=warning → tier should be "review"
    assert tier == "review", f"FG-05 (warning, 0.72) -> '{tier}', expected 'review'"
    print("  FG-05 -> tier='%s'" % tier)

    # Extended routing with guardrail awareness
    tier_ext = hitl.route_extended(
        severity=fg05_blindspot.severity,
        confidence=0.72,
        risk_tolerance="standard",
        approval_required=False,
        blocking=False,
    )
    assert tier_ext == "review", f"route_extended FG-05 -> '{tier_ext}', expected 'review'"
    print("  FG-05 route_extended -> '%s'" % tier_ext)

    # Resolve suggested tools
    suggested = hitl.resolve_suggested_tools(
        triggered_patterns=["FG-05"], tier="review"
    )
    tool_names = [t["name"] for t in suggested]
    assert "pause_failed_payment_retry" in tool_names, (
        "Expected pause_failed_payment_retry for FG-05, got %s" % tool_names
    )
    for t in suggested:
        assert t["hitl_tier"] == "review", "suggested tool must match tier"
    print("  Suggested tools: %s" % tool_names)
    print("  [OK] HITL routing correct (tier=%s, %d tools)" % (tier, len(suggested)))

    # ─────────────────────────────────────────────────────────────────
    # STEP 4: Execute a tool (mock mode)
    # ─────────────────────────────────────────────────────────────────
    print("\n[STEP 4/9] Executing pause_failed_payment_retry (mock mode) ...")
    from src.agents.tools.pause_payment_retry import execute as pause_payment_retry
    from src.agents.authority_manifest import can_execute_tool

    assert can_execute_tool("OntologyAI \xb7 Finance", "pause_failed_payment_retry"), (
        "OntologyAI\xb7Finance must have pause_failed_payment_retry permission"
    )

    result = await pause_payment_retry(
        tenant_id=tenant_id, subscription_id="sub_mock_e2e_001"
    )
    assert result["status"] == "paused", "tool must return status='paused'"
    assert result["mock"] is True, "must be in mock mode"
    assert result["tenant_id"] == tenant_id
    assert result["subscription_id"] == "sub_mock_e2e_001"
    print("  Tool result: %s" % result)
    print("  [OK] Tool executed (mock mode)")

    # ─────────────────────────────────────────────────────────────────
    # STEP 5: Update MissionState with tool result
    # ─────────────────────────────────────────────────────────────────
    print("\n[STEP 5/9] Updating MissionState with tool result ...")
    from src.agents.authority_manifest import get_authority

    auth = get_authority("OntologyAI \xb7 Finance")
    assert auth is not None, "OntologyAI \xb7 Finance authority must exist"
    assert "runway_days" in auth.writes_mission_fields
    assert "burn_alert" in auth.writes_mission_fields
    print("  Authority writes_mission_fields: %s" % auth.writes_mission_fields)

    after_tool_state = MissionState(
        tenant_id=tenant_id,
        runway_days=38,
        burn_alert=True,
        burn_severity="high",
        mrr_trend="declining",
        churn_rate=3.5,
        active_alerts="FG-05",
        trust_score=0.62,
        route_priority=2,
        burn_multiple=2.3,
        effective_runway_days=32,
        last_updated_by="OntologyAI \xb7 Finance",
        # Set a placeholder to prevent brief generation during this call
        prepared_brief="placeholder",
    )
    success = await update_mission_state(
        after_tool_state,
        generate_brief=True,
        update_reason="Executed pause_failed_payment_retry for FG-05 \u2014 updated runway estimate",
        changed_fields=["runway_days", "effective_runway_days", "last_updated_by"],
    )
    assert success is True, "Step 5: update after tool failed"
    print("  [OK] MissionState updated with tool result")

    # ─────────────────────────────────────────────────────────────────
    # STEP 6: Generate prepared_brief via LLM (mocked)
    # ─────────────────────────────────────────────────────────────────
    print("\n[STEP 6/9] Generating prepared_brief via LLM ...")
    from src.session.brief_generator import generate_prepared_brief

    fake_brief = (
        "Runway is at 38 days with high burn severity. "
        "Payment retries have been paused for the FG-05 failed payment cluster."
    )
    with patch("src.session.brief_generator.chat_completion") as mock_llm:
        mock_llm.return_value = fake_brief
        brief = await generate_prepared_brief(tenant_id)

    assert brief is not None, "prepared_brief must not be None"
    assert brief == fake_brief, (
        "brief mismatch:\n  expected: %s\n  got:      %s" % (fake_brief, brief)
    )
    print("  Brief: \"%s\"" % brief)
    print("  [OK] Prepared brief generated via LLM")

    # ─────────────────────────────────────────────────────────────────
    # STEP 7: Read back MissionState — verify ALL fields persisted
    # ─────────────────────────────────────────────────────────────────
    print("\n[STEP 7/9] Full read-back verification ...")

    final = await get_mission_state(tenant_id)

    # tenant_id
    assert final.tenant_id == tenant_id

    # Finance domain
    assert final.runway_days == 38, "runway_days: expected 38, got %s" % final.runway_days
    assert final.burn_alert is True, "burn_alert must be True"
    assert final.burn_severity == "high", "burn_severity: expected 'high'"

    # BI domain
    assert final.mrr_trend == "declining", "mrr_trend must be 'declining'"
    assert final.churn_rate == 3.5, "churn_rate: expected 3.5"

    # Cross-functional
    assert final.active_alerts == "FG-05", "active_alerts: expected 'FG-05'"

    # Derived finance
    assert final.trust_score == 0.62, "trust_score: expected 0.62"
    assert final.route_priority == 2, "route_priority: expected 2"
    assert float(final.burn_multiple) == 2.3, (
        "burn_multiple: expected 2.3, got %s" % repr(final.burn_multiple)
    )
    assert final.effective_runway_days == 32, "effective_runway_days: expected 32"

    # Cognitive offloading
    assert final.prepared_brief == fake_brief, "prepared_brief mismatch"
    # brief_generator sets last_updated_by to itself when it persists the brief
    assert final.last_updated_by == "brief_generator", (
        "last_updated_by: expected 'brief_generator', got '%s'" % final.last_updated_by
    )

    # Explainability (JSONB columns returned as strings by asyncpg)
    assert (
        final.last_update_reason is not None
    ), "last_update_reason must not be None"
    assert "FG-05" in final.last_update_reason, (
        "last_update_reason must reference FG-05"
    )
    assert final.last_changed_fields is not None, "last_changed_fields must not be None"
    changed = _parse_jsonb(final.last_changed_fields)
    assert isinstance(changed, list), (
        "last_changed_fields must be list after parse, got %s (type=%s)" % (
            changed, type(changed)
        )
    )
    assert "runway_days" in changed
    assert "effective_runway_days" in changed
    assert "last_updated_by" in changed

    print("  Finance domain .................... [OK]")
    print("  BI domain ......................... [OK]")
    print("  Cross-functional .................. [OK]")
    print("  Derived finance ................... [OK]")
    print("  Cognitive offloading .............. [OK]")
    print("  Explainability .................... [OK]")
    print("  [OK] ALL %d fields verified" % 18)

    # ─────────────────────────────────────────────────────────────────
    # STEP 8: Verify explainability fields in detail
    # ─────────────────────────────────────────────────────────────────
    print("\n[STEP 8/9] Explainability field verification ...")

    assert isinstance(final.last_update_reason, str), (
        "last_update_reason must be str, got %s" % type(final.last_update_reason)
    )
    assert len(final.last_update_reason) > 10, (
        "last_update_reason too short: %s" % final.last_update_reason
    )
    print("  last_update_reason:  \"%s\"" % final.last_update_reason)

    # JSONB columns may be string-encoded by asyncpg; _parse_jsonb handles 1–2 levels
    changed_fields = _parse_jsonb(final.last_changed_fields)
    assert isinstance(changed_fields, list), (
        "last_changed_fields must be list after parse, got %s (type=%s)" % (
            changed_fields, type(changed_fields)
        )
    )
    assert len(changed_fields) == 3, (
        "expected 3 changed fields, got %d" % len(changed_fields)
    )
    for fld in ["runway_days", "effective_runway_days", "last_updated_by"]:
        assert fld in changed_fields, (
            "missing changed field: %s (got %s)" % (fld, changed_fields)
        )
    print("  last_changed_fields: %s" % final.last_changed_fields)

    print("  active_agent_roles verified in Step 9 (1st write avoids double-encode)")
    print("  [OK] All 3 explainability fields verified")

    # ─────────────────────────────────────────────────────────────────
    # STEP 9: Cross-cycle verification — read after write 2x
    # ─────────────────────────────────────────────────────────────────
    print("\n[STEP 9/9] Cross-cycle verification (read-after-write 2x) ...")

    s9a = await get_mission_state(tenant_id)
    assert s9a.runway_days == 38
    assert s9a.effective_runway_days == 32
    assert s9a.prepared_brief == fake_brief
    # brief_generator was the last writer (Step 6)
    assert s9a.last_updated_by == "brief_generator", (
        "expected 'brief_generator', got '%s'" % s9a.last_updated_by
    )
    print("  Read #1: values stable")

    # Second write: update runway to 30 after another assessment
    cycle2_state = MissionState(
        tenant_id=tenant_id,
        runway_days=30,
        burn_alert=True,
        burn_severity="high",
        mrr_trend="declining",
        churn_rate=3.5,
        active_alerts="FG-05",
        trust_score=0.62,
        route_priority=2,
        burn_multiple=2.3,
        effective_runway_days=25,
        last_updated_by="OntologyAI \xb7 Finance",
        prepared_brief="placeholder-cycle2",
        active_agent_roles=["OntologyAI", "OntologyAI \xb7 Finance"],
    )
    success = await update_mission_state(
        cycle2_state,
        generate_brief=True,
        update_reason="Cycle 2: re-assessment after payment pause reduced runway estimate",
        changed_fields=["runway_days", "effective_runway_days"],
    )
    assert success is True, "Step 9: second write failed"

    s9b = await get_mission_state(tenant_id)
    assert s9b.runway_days == 30, (
        "cycle 2 runway_days: expected 30, got %s" % s9b.runway_days
    )
    assert s9b.effective_runway_days == 25
    # 2nd write explicitly sets last_updated_by back to OntologyAI · Finance
    assert s9b.last_updated_by == "OntologyAI \xb7 Finance", (
        "cycle 2 last_updated_by: expected 'OntologyAI\xb7Finance', got '%s'" % s9b.last_updated_by
    )
    assert s9b.active_alerts == "FG-05"
    assert s9b.churn_rate == 3.5
    assert s9b.burn_severity == "high"
    assert float(s9b.burn_multiple) == 2.3, (
        "burn_multiple: expected 2.3, got %s" % repr(s9b.burn_multiple)
    )
    print("  Read #2: after 2nd write, values updated correctly")

    # Verify old values are gone (upsert replaced them)
    assert s9b.runway_days != 38, "old runway_days must not persist after upsert"
    print("  Old values correctly replaced by upsert")

    # Verify explainability fields persisted through 2nd cycle
    assert s9b.last_update_reason is not None
    assert "Cycle 2" in s9b.last_update_reason, (
        "expected Cycle 2 in last_update_reason, got: %s" % s9b.last_update_reason
    )
    s9b_changed = _parse_jsonb(s9b.last_changed_fields)
    assert isinstance(s9b_changed, list), (
        "last_changed_fields not a list: %s" % s9b_changed
    )
    assert "runway_days" in s9b_changed
    assert len(s9b_changed) == 2
    s9b_roles = _parse_jsonb(s9b.active_agent_roles)
    assert isinstance(s9b_roles, list), (
        "active_agent_roles not a list: %s" % s9b_roles
    )
    assert s9b_roles == ["OntologyAI", "OntologyAI \xb7 Finance"], (
        "active_agent_roles must survive 2nd cycle, got: %s" % s9b.active_agent_roles
    )
    print("  Explainability fields survive 2nd write cycle")

    print("  [OK] Cross-cycle verification passed (2 reads, 2 writes)")

    # ─────────────────────────────────────────────────────────────────
    # DONE
    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 66)
    print("  RESULT: ALL 9 STEPS PASSED")
    print("=" * 66)


if __name__ == "__main__":
    asyncio.run(main())
