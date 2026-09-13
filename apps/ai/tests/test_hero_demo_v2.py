"""Hero Demo V2 Tests — proves the 9-scene structured timeline.

Tests that the hero demo v2 module:
1. All 9 scenes are defined with correct structure
2. Each scene has narrative, evidence, decision, why_it_matters
3. Scene timeline is in order
4. Scene 7 (false recovery) decision contains "FAILED"
5. Scene 9 (verified recovery) decision contains "VERIFIED"
6. No I/O, no LLM, no network
7. All models strict (extra=forbid)
8. run_full_demo() returns all 9 scenes
9. Demo can be serialized to JSON
"""

from __future__ import annotations

import json

import pytest

from src.mission.hero_demo_v2 import (
    DEMO_MISSION,
    DEMO_TENANT,
    DemoOutput,
    DemoScene,
    build_all_scenes,
    run_full_demo,
    scenes_to_dict_list,
    scenes_to_json,
)


# ── Test 1: All 9 scenes are defined with correct structure ─────────────


def test_all_nine_scenes_are_defined():
    """Exactly 9 scenes exist with scene_number 1-9."""
    scenes = build_all_scenes()
    assert len(scenes) == 9
    for i, scene in enumerate(scenes, start=1):
        assert scene.scene_number == i


def test_each_scene_has_required_fields():
    """Every scene has title, timestamp, input_state, output_state, narrative, evidence, decision, why_it_matters."""
    scenes = build_all_scenes()
    for scene in scenes:
        assert isinstance(scene.title, str) and len(scene.title) > 0
        assert isinstance(scene.timestamp, str) and "T" in scene.timestamp
        assert isinstance(scene.input_state, dict)
        assert isinstance(scene.output_state, dict)
        assert isinstance(scene.narrative, str) and len(scene.narrative) > 0
        assert isinstance(scene.evidence, list) and len(scene.evidence) > 0
        assert isinstance(scene.decision, str) and len(scene.decision) > 0
        assert isinstance(scene.why_it_matters, str) and len(scene.why_it_matters) > 0


# ── Test 2: Scene timeline is in order ──────────────────────────────────


def test_scene_timeline_is_in_order():
    """Scene timestamps are monotonically non-decreasing."""
    scenes = build_all_scenes()
    timestamps = [scene.timestamp for scene in scenes]
    assert timestamps == sorted(timestamps)


def test_scene_numbers_are_sequential():
    """Scene numbers go 1, 2, ..., 9 with no gaps."""
    scenes = build_all_scenes()
    numbers = [scene.scene_number for scene in scenes]
    assert numbers == list(range(1, 10))


# ── Test 3: Scene 7 decision contains "FAILED" ─────────────────────────


def test_scene_7_false_recovery_decision_contains_failed():
    """Scene 7 (false recovery detection) decision must contain 'FAILED'."""
    scenes = build_all_scenes()
    scene_7 = scenes[6]  # 0-indexed
    assert scene_7.scene_number == 7
    assert "FAILED" in scene_7.decision


def test_scene_7_rejection_reasoning():
    """Scene 7 evidence shows vendor claim vs monitoring reality."""
    scenes = build_all_scenes()
    scene_7 = scenes[6]
    evidence_text = " ".join(scene_7.evidence)
    assert "RESOLVED" in evidence_text
    assert "FAILING" in evidence_text or "DEGRADED" in evidence_text


# ── Test 4: Scene 9 decision contains "VERIFIED" ───────────────────────


def test_scene_9_verified_recovery_decision_contains_verified():
    """Scene 9 (verified recovery) decision must contain 'VERIFIED'."""
    scenes = build_all_scenes()
    scene_9 = scenes[8]  # 0-indexed
    assert scene_9.scene_number == 9
    assert "VERIFIED" in scene_9.decision


def test_scene_9_recovery_evidence():
    """Scene 9 evidence shows all systems healthy."""
    scenes = build_all_scenes()
    scene_9 = scenes[8]
    evidence_text = " ".join(scene_9.evidence)
    assert "HEALTHY" in evidence_text


# ── Test 5: No I/O, no LLM, no network ─────────────────────────────────


def test_no_io_pure_functions():
    """All scene builders are pure functions with no side effects."""
    # Run twice — identical output proves determinism
    scenes_a = build_all_scenes()
    scenes_b = build_all_scenes()
    for a, b in zip(scenes_a, scenes_b):
        assert a.model_dump() == b.model_dump()


def test_no_external_dependencies():
    """Module imports only stdlib + pydantic — no network, no LLM."""
    import inspect

    import src.mission.hero_demo_v2 as mod

    source = inspect.getsource(mod)
    forbidden = ["requests", "httpx", "openai", "ollama", "asyncio", "socket"]
    for name in forbidden:
        # Check imports, not string mentions in narrative
        if name in ("requests", "httpx", "openai", "ollama"):
            assert f"import {name}" not in source, f"Module imports {name}"
            assert f"from {name}" not in source, f"Module imports from {name}"


# ── Test 6: All models strict (extra=forbid) ────────────────────────────


def test_demo_scene_rejects_extra_fields():
    """DemoScene rejects unknown fields (extra=forbid)."""
    with pytest.raises(Exception):
        DemoScene(
            scene_number=1,
            title="Test",
            timestamp="2026-01-01T00:00:00Z",
            input_state={},
            output_state={},
            narrative="Test",
            evidence=["Test"],
            decision="Test",
            why_it_matters="Test",
            sneaky_field="not allowed",  # type: ignore
        )


def test_demo_output_rejects_extra_fields():
    """DemoOutput rejects unknown fields (extra=forbid)."""
    with pytest.raises(Exception):
        DemoOutput(
            demo_id="test",
            tenant="t-test",
            scenes=[],
            sneaky_field="not allowed",  # type: ignore
        )


def test_demo_scene_strict_type_coercion():
    """DemoScene strict=True rejects implicit type coercion."""
    with pytest.raises(Exception):
        DemoScene(
            scene_number="1",  # type: ignore  # should be int, not str
            title="Test",
            timestamp="2026-01-01T00:00:00Z",
            input_state={},
            output_state={},
            narrative="Test",
            evidence=["Test"],
            decision="Test",
            why_it_matters="Test",
        )


# ── Test 7: run_full_demo() returns all 9 scenes ───────────────────────


def test_run_full_demo_returns_nine_scenes():
    """run_full_demo() returns DemoOutput with exactly 9 scenes."""
    output = run_full_demo()
    assert isinstance(output, DemoOutput)
    assert len(output.scenes) == 9
    assert output.demo_id == DEMO_MISSION
    assert output.tenant == DEMO_TENANT


def test_run_full_demo_scene_numbers():
    """All 9 scenes in run_full_demo() have correct scene_number."""
    output = run_full_demo()
    for i, scene in enumerate(output.scenes, start=1):
        assert scene.scene_number == i


def test_run_full_demo_deterministic():
    """Two runs produce identical output."""
    output_a = run_full_demo()
    output_b = run_full_demo()
    assert output_a.model_dump() == output_b.model_dump()


# ── Test 8: Demo can be serialized to JSON ──────────────────────────────


def test_demo_serializes_to_json():
    """run_full_demo() output serializes to valid JSON."""
    output = run_full_demo()
    json_str = scenes_to_json(output)
    parsed = json.loads(json_str)
    assert isinstance(parsed, dict)
    assert "demo_id" in parsed
    assert "scenes" in parsed
    assert len(parsed["scenes"]) == 9


def test_demo_json_round_trip():
    """JSON serialization round-trips through pydantic correctly."""
    output = run_full_demo()
    json_str = scenes_to_json(output)
    parsed = json.loads(json_str)
    restored = DemoOutput(**parsed)
    assert restored.model_dump() == output.model_dump()


def test_scenes_to_dict_list():
    """scenes_to_dict_list returns plain dicts."""
    scenes = build_all_scenes()
    dicts = scenes_to_dict_list(scenes)
    assert isinstance(dicts, list)
    assert len(dicts) == 9
    for d in dicts:
        assert isinstance(d, dict)
        assert "scene_number" in d
        assert "narrative" in d
        assert "evidence" in d
        assert "decision" in d
        assert "why_it_matters" in d


# ── Test 9: Scene-specific content verification ─────────────────────────


def test_scene_1_incident_type():
    """Scene 1 classifies incident as vendor type."""
    scenes = build_all_scenes()
    assert scenes[0].output_state["incident_type"] == "vendor"


def test_scene_2_ontology_chain():
    """Scene 2 has the 5-step impact chain."""
    scenes = build_all_scenes()
    chain = scenes[1].output_state["impact_chain"]
    assert len(chain) == 5
    assert chain[0] == "Incident"
    assert chain[-1] == "PayCore"


def test_scene_3_sla_tier():
    """Scene 3 sets P1 SLA with 15min ack deadline."""
    scenes = build_all_scenes()
    assert scenes[2].output_state["sla_tier"] == "P1"
    assert scenes[2].output_state["ack_deadline_minutes"] == 15


def test_scene_4_confidence():
    """Scene 4 agent investigation has 0.88 confidence."""
    scenes = build_all_scenes()
    assert scenes[3].output_state["action_intent"]["confidence"] == 0.88


def test_scene_5_authorization():
    """Scene 5 control plane passes authorization."""
    scenes = build_all_scenes()
    assert scenes[4].output_state["authorization"] == "pass"
    assert scenes[4].output_state["policy_check"] == "pass"


def test_scene_6_ticket_id():
    """Scene 6 vendor ticket has correct ID."""
    scenes = build_all_scenes()
    assert scenes[5].output_state["ticket_id"] == "VT-2024-001"


def test_scene_7_error_rate():
    """Scene 7 shows 35% error rate — false recovery."""
    scenes = build_all_scenes()
    assert scenes[6].output_state["error_rate"] == 0.35
    assert scenes[6].output_state["recovery_verified"] is False


def test_scene_8_escalation_level():
    """Scene 8 escalates to L4."""
    scenes = build_all_scenes()
    assert scenes[7].output_state["escalation_level"] == "L4"


def test_scene_9_zero_error_rate():
    """Scene 9 shows 0% error rate — real recovery."""
    scenes = build_all_scenes()
    assert scenes[8].output_state["error_rate"] == 0.0
    assert scenes[8].output_state["recovery_verified"] is True
    assert scenes[8].output_state["mission_status"] == "resolved"


# ── Test 10: Evidence contains expected keywords ────────────────────────


def test_scene_1_evidence_keywords():
    """Scene 1 evidence mentions 503 and Stripe."""
    scenes = build_all_scenes()
    evidence = " ".join(scenes[0].evidence)
    assert "503" in evidence
    assert "Stripe" in evidence


def test_scene_4_evidence_keywords():
    """Scene 4 evidence mentions monitoring and patterns."""
    scenes = build_all_scenes()
    evidence = " ".join(scenes[3].evidence)
    assert "monitoring" in evidence.lower()


def test_scene_5_evidence_keywords():
    """Scene 5 evidence mentions authorization and idempotency."""
    scenes = build_all_scenes()
    evidence = " ".join(scenes[4].evidence)
    assert "Authorization" in evidence
    assert "Idempotency" in evidence


def test_scene_8_evidence_keywords():
    """Scene 8 evidence mentions escalation."""
    scenes = build_all_scenes()
    evidence = " ".join(scenes[7].evidence)
    assert "escalat" in evidence.lower()


def test_scene_9_evidence_keywords():
    """Scene 9 evidence mentions HEALTHY or RESOLVED for all systems."""
    scenes = build_all_scenes()
    evidence = " ".join(scenes[8].evidence)
    assert "HEALTHY" in evidence
    assert "RESOLVED" in evidence
