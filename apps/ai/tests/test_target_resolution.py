"""Phase 1 dual-write: generic mission/checkpoint targets with onboarding alias.

Covers: generic target path, onboarding-compat dual-write, contradictory
rejection, blank handling, Mission resolution (both models), checkpoint
resolution. Additive only — no existing test file is touched.
"""

import pytest

from src.context.assemble import assemble_checkpoint
from src.entities.models import Mission as EntityMission
from src.mission.blocker_investigation_mission import (
    build_context_checkpoint,
    resolve_checkpoint_target,
)
from src.ontology.object_types import Evidence, Mission, Onboarding


def _onboarding(ob_id: str = "ob-1") -> Onboarding:
    return Onboarding(
        id=ob_id,
        customer="acme",
        stakeholders=["alice"],
        requirements=["SSO config"],
        tasks=["t-1"],
        issues=["PROJ-1"],
        missions=["m-1"],
        lifecycle_state="implementing",
    )


def _evidence(ev_id: str = "ev-1") -> Evidence:
    return Evidence(
        id=ev_id,
        tenant_id="t-1",
        source="slack",
        provenance="slack:general:alice",
        captured_at="2026-09-09T00:00:00Z",
        raw_text="delivery blocked",
        normalized_text="[slack report]: delivery blocked",
    )


# ── Mission target resolution (ontology model) ────────────────────────────


class TestOntologyMissionTarget:
    def test_generic_target_path(self):
        m = Mission(id="m-1", title="t", target_type="vendor", target_id="v-9")
        assert (m.target_type, m.target_id) == ("vendor", "v-9")
        assert m.onboarding_id is None

    def test_onboarding_compat_dual_write(self):
        m = Mission(id="m-1", title="t", onboarding_id="ob-1")
        assert m.onboarding_id == "ob-1"
        assert (m.target_type, m.target_id) == ("onboarding", "ob-1")

    def test_contradictory_inputs_rejected(self):
        with pytest.raises(ValueError):
            Mission(
                id="m-1",
                title="t",
                onboarding_id="ob-1",
                target_type="onboarding",
                target_id="ob-2",
            )

    def test_generic_target_coexists_with_onboarding_alias(self):
        m = Mission(
            id="m-1",
            title="t",
            onboarding_id="ob-1",
            target_type="vendor",
            target_id="v-9",
        )
        assert (m.target_type, m.target_id) == ("vendor", "v-9")
        assert m.onboarding_id == "ob-1"

    def test_blank_targets_allowed(self):
        m = Mission(id="m-1", title="t")
        assert m.target_type is None
        assert m.target_id is None
        assert m.onboarding_id is None

    def test_matching_explicit_onboarding_accepted(self):
        m = Mission(
            id="m-1",
            title="t",
            onboarding_id="ob-1",
            target_type="onboarding",
            target_id="ob-1",
        )
        assert (m.target_type, m.target_id) == ("onboarding", "ob-1")


# ── Mission target resolution (entities model) ────────────────────────────


class TestEntityMissionTarget:
    def test_generic_target_path(self):
        m = EntityMission(
            id="m-1", tenant_id="t-1", title="t",
            target_type="vendor", target_id="v-9",
        )
        assert (m.target_type, m.target_id) == ("vendor", "v-9")
        assert m.onboarding_id is None

    def test_onboarding_compat_dual_write(self):
        m = EntityMission(
            id="m-1", tenant_id="t-1", title="t", onboarding_id="ob-1"
        )
        assert m.onboarding_id == "ob-1"
        assert (m.target_type, m.target_id) == ("onboarding", "ob-1")

    def test_contradictory_inputs_rejected(self):
        with pytest.raises(ValueError):
            EntityMission(
                id="m-1",
                tenant_id="t-1",
                title="t",
                onboarding_id="ob-1",
                target_type="onboarding",
                target_id="ob-2",
            )

    def test_blank_targets_allowed(self):
        m = EntityMission(id="m-1", tenant_id="t-1", title="t")
        assert m.target_type is None
        assert m.target_id is None
        assert m.onboarding_id is None


# ── Checkpoint target resolution ──────────────────────────────────────────


class TestResolveCheckpointTarget:
    def test_generic_target_wins(self):
        assert resolve_checkpoint_target(
            _onboarding("ob-1"), "vendor", "v-9"
        ) == ("vendor", "v-9")

    def test_onboarding_fallback_dual_writes(self):
        assert resolve_checkpoint_target(_onboarding("ob-1")) == (
            "onboarding",
            "ob-1",
        )

    def test_contradictory_inputs_rejected(self):
        with pytest.raises(ValueError):
            resolve_checkpoint_target(
                _onboarding("ob-1"), "onboarding", "ob-2"
            )

    def test_blank_allowed_without_onboarding(self):
        assert resolve_checkpoint_target(None) == (None, None)


class TestBuildContextCheckpoint:
    def test_onboarding_behavior_preserved_with_derived_target(self):
        cp = build_context_checkpoint(_onboarding("ob-1"), "m-1", [_evidence()])
        assert cp["onboarding_id"] == "ob-1"
        assert cp["target_type"] == "onboarding"
        assert cp["target_id"] == "ob-1"
        assert cp["mission_id"] == "m-1"
        assert cp["evidence_refs"] == ["ev-1"]

    def test_explicit_matching_target_accepted(self):
        cp = build_context_checkpoint(
            _onboarding("ob-1"),
            "m-1",
            [_evidence()],
            target_type="onboarding",
            target_id="ob-1",
        )
        assert (cp["target_type"], cp["target_id"]) == ("onboarding", "ob-1")

    def test_contradictory_target_rejected(self):
        with pytest.raises(ValueError):
            build_context_checkpoint(
                _onboarding("ob-1"),
                "m-1",
                [_evidence()],
                target_type="onboarding",
                target_id="ob-2",
            )


class TestAssembleCheckpointTargets:
    def test_explicit_targets_forwarded(self):
        from datetime import datetime, timezone

        cp = assemble_checkpoint(
            checkpoint_id="cp-1",
            tenant_id="t-1",
            mission_id="m-1",
            trigger_event_id="ev-1",
            evidence=[_evidence()],
            now=datetime(2026, 9, 9, 1, 0, 0, tzinfo=timezone.utc),
            onboarding=_onboarding("ob-1"),
            target_type="vendor",
            target_id="v-9",
        )
        assert (cp.target_type, cp.target_id) == ("vendor", "v-9")

    def test_onboarding_derives_target(self):
        from datetime import datetime, timezone

        cp = assemble_checkpoint(
            checkpoint_id="cp-1",
            tenant_id="t-1",
            mission_id="m-1",
            trigger_event_id="ev-1",
            evidence=[_evidence()],
            now=datetime(2026, 9, 9, 1, 0, 0, tzinfo=timezone.utc),
            onboarding=_onboarding("ob-1"),
        )
        assert (cp.target_type, cp.target_id) == ("onboarding", "ob-1")
