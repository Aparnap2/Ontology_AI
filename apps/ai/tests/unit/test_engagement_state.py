"""TDD tests for EngagementState schema (PRD §14.1 / §14.2).

Tests the canonical shared state shape, deterministic patch merge,
and BABOK artifact versioning.

Key behaviors asserted:
  * Minimal and full-field creation
  * merge_patch rejects unknown keys and immutable fields
  * List fields are appended, dict fields deep-merged
  * BABOK artifact protection: finalized artifacts guarded from append
  * add_artifact_version replaces finalized artifacts safely
  * Serialization round-trip (model_dump -> model_validate)
"""
import copy
import pytest
from pydantic import ValidationError

from src.schemas.engagement_state import (
    EngagementState,
    merge_patch,
    _ALLOWED_PATCH_KEYS,
    _BABOK_ARTIFACT_PATCH_KEYS,
)


def _make_minimal(**overrides):
    kwargs = dict(
        engagement_id="e1",
        tenant_id="t1",
        workspace_mode="workspace",
    )
    kwargs.update(overrides)
    return EngagementState.create(**kwargs)


def _make_full(**overrides):
    """Create EngagementState with all optional fields populated."""
    kwargs = dict(
        engagement_id="e-full",
        tenant_id="t-full",
        workspace_mode="workspace",
        operator_goal="Map customer journey",
    )
    kwargs.update(overrides)
    state = EngagementState.create(**kwargs)
    return state


def _make_babok_artifact(
    artifact_id="ba-1",
    title="Current State Analysis",
    status="approved",
):
    return {
        "artifact_id": artifact_id,
        "title": title,
        "status": status,
        "content": "Analysis content",
    }


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

class TestEngagementStateCreation:
    def test_create_minimal(self):
        state = _make_minimal()
        assert state.engagement_id == "e1"
        assert state.tenant_id == "t1"
        assert state.workspace_mode == "workspace"
        assert state.phase == "discovery"
        assert state.operator_goal is None

    def test_create_with_all_fields(self):
        state = _make_full()
        assert state.engagement_id == "e-full"
        assert state.tenant_id == "t-full"
        assert state.operator_goal == "Map customer journey"

    def test_create_with_operator_goal(self):
        state = _make_minimal(operator_goal="Onboard Acme Corp")
        assert state.operator_goal == "Onboard Acme Corp"

    def test_default_lists_are_empty(self):
        state = _make_minimal()
        assert state.discovery_notes == []
        assert state.ontology_objects == {}
        assert state.ontology_links == []
        assert state.truth_findings == []
        assert state.workflow_specs == []
        assert state.executable_workflow_drafts == []
        assert state.planned_actions == []
        assert state.unresolved_questions == []
        assert state.data_sources == []
        assert state.freshness == {}

    def test_default_babok_lists_are_empty(self):
        state = _make_minimal()
        assert state.current_state_descriptions == []
        assert state.business_objectives == []
        assert state.risk_analyses == []
        assert state.change_strategies == []
        assert state.solution_evaluations == []

    def test_updated_at_set_on_creation(self):
        state = _make_minimal()
        assert state.updated_at != ""
        assert "T" in state.updated_at  # ISO format

    def test_create_requires_engagement_id(self):
        """engagement_id missing should raise TypeError (required positional arg)."""
        with pytest.raises((ValidationError, TypeError)):
            EngagementState.create(tenant_id="t1", workspace_mode="workspace")

    def test_create_requires_tenant_id(self):
        """tenant_id missing should raise TypeError (required positional arg)."""
        with pytest.raises((ValidationError, TypeError)):
            EngagementState.create(engagement_id="e1", workspace_mode="workspace")


class TestEngagementStateFieldValidation:
    def test_rejects_unknown_fields(self):
        with pytest.raises(ValidationError):
            EngagementState(
                engagement_id="e1",
                tenant_id="t1",
                workspace_mode="fde_assisted",
                phase="discovery",
                nonexistent_field="value",
            )

    def test_rejects_invalid_phase(self):
        with pytest.raises(ValidationError):
            EngagementState(
                engagement_id="e1",
                tenant_id="t1",
                workspace_mode="fde_assisted",
                phase="invalid_phase",
            )

    def test_rejects_invalid_workspace_mode(self):
        with pytest.raises(ValidationError):
            EngagementState(
                engagement_id="e1",
                tenant_id="t1",
                workspace_mode="invalid_mode",
                phase="discovery",
            )

    def test_all_phases_accepted(self):
        for phase in [
            "discovery", "ontology_mapping", "truth_analysis",
            "workflow_design", "governance_review", "deployment_planning", "handoff",
        ]:
            state = EngagementState(
                engagement_id="e1",
                tenant_id="t1",
                workspace_mode="fde_assisted",
                phase=phase,
            )
            assert state.phase == phase

    def test_all_workspace_modes_accepted(self):
        for mode in ["dashboard", "workspace"]:
            state = _make_minimal(workspace_mode=mode)
            assert state.workspace_mode == mode


# ---------------------------------------------------------------------------
# merge_patch tests
# ---------------------------------------------------------------------------

class TestMergePatch:
    def test_merge_patch_adds_phase(self):
        state = _make_minimal()
        merged = state.merge_patch({"phase": "ontology_mapping"})
        assert merged.phase == "ontology_mapping"
        assert merged.engagement_id == state.engagement_id  # unchanged

    def test_merge_patch_appends_list(self):
        state = _make_minimal()
        merged = state.merge_patch({"discovery_notes": [{"ref": "n1", "content": "Note 1"}]})
        assert len(merged.discovery_notes) == 1
        assert merged.discovery_notes[0]["ref"] == "n1"

    def test_merge_patch_appends_to_existing_list(self):
        state = _make_minimal()
        state = state.merge_patch({"discovery_notes": [{"ref": "n1", "content": "Note 1"}]})
        merged = state.merge_patch({"discovery_notes": [{"ref": "n2", "content": "Note 2"}]})
        assert len(merged.discovery_notes) == 2

    def test_merge_patch_rejects_unknown_keys(self):
        state = _make_minimal()
        with pytest.raises(ValueError, match="Unknown patch keys"):
            state.merge_patch({"bogus_key": "value"})

    def test_merge_patch_rejects_workspace_mode_change(self):
        state = _make_minimal()
        with pytest.raises(ValueError, match="immutable"):
            state.merge_patch({"workspace_mode": "workspace"})

    def test_merge_patch_non_dict_raises(self):
        state = _make_minimal()
        with pytest.raises(ValueError, match="patch must be a dict"):
            state.merge_patch("not a dict")

    def test_merge_patch_deep_merges_dicts(self):
        state = _make_minimal()
        state = state.merge_patch({"freshness": {"discovery": "2024-01-01T00:00:00"}})
        merged = state.merge_patch({"freshness": {"governance": "2024-01-02T00:00:00"}})
        assert "discovery" in merged.freshness
        assert "governance" in merged.freshness

    def test_merge_patch_updates_updated_at(self):
        state = _make_minimal()
        original_updated = state.updated_at
        merged = state.merge_patch({"phase": "ontology_mapping"})
        assert merged.updated_at >= original_updated

    def test_merge_patch_adds_provenance_to_freshness(self):
        state = _make_minimal()
        merged = state.merge_patch({"phase": "ontology_mapping"}, provenance="ChiefOfStaff")
        assert "ChiefOfStaff" in merged.freshness

    def test_module_level_merge_patch_works(self):
        state = _make_minimal()
        merged = merge_patch(state, {"phase": "ontology_mapping"}, provenance="Test")
        assert isinstance(merged, EngagementState)
        assert merged.phase == "ontology_mapping"

    def test_module_level_merge_patch_raises_on_non_state(self):
        with pytest.raises(TypeError, match="must be an EngagementState"):
            merge_patch({"not": "state"}, {"phase": "discovery"})

    def test_merge_patch_immutability_of_original(self):
        """The original state must not be mutated by merge_patch."""
        state = _make_minimal()
        original_phase = state.phase
        state.merge_patch({"phase": "ontology_mapping"})
        assert state.phase == original_phase, "Original state was mutated!"


# ---------------------------------------------------------------------------
# BABOK artifact protection tests
# ---------------------------------------------------------------------------

class TestBabokArtifactProtection:
    """Finalized BABOK artifacts cannot be overwritten by append-only merge."""

    def test_append_to_finalized_artifact_raises(self):
        state = _make_minimal()
        finalized = _make_babok_artifact(artifact_id="ba-1", status="approved")
        state = state.merge_patch({"current_state_descriptions": [finalized]})
        with pytest.raises(ValueError, match="finalized artifact"):
            state.merge_patch({"current_state_descriptions": [{"artifact_id": "ba-2"}]})

    def test_append_to_non_finalized_artifact_succeeds(self):
        state = _make_minimal()
        draft = _make_babok_artifact(artifact_id="ba-1", status="proposed")
        state = state.merge_patch({"current_state_descriptions": [draft]})
        merged = state.merge_patch({"current_state_descriptions": [{"artifact_id": "ba-2"}]})
        assert len(merged.current_state_descriptions) == 2

    def test_all_babok_fields_are_protected(self):
        for field in _BABOK_ARTIFACT_PATCH_KEYS:
            state = _make_minimal()
            finalized = _make_babok_artifact(artifact_id="ba-1", status="approved")
            state = state.merge_patch({field: [finalized]})
            with pytest.raises(ValueError, match="finalized artifact"):
                state.merge_patch({field: [{"artifact_id": "ba-2"}]})

    def test_non_babok_field_not_protected(self):
        """discovery_notes is not a BABOK field, so finalized-like entries don't block."""
        state = _make_minimal()
        state = state.merge_patch({"discovery_notes": [{"ref": "n1", "status": "approved"}]})
        merged = state.merge_patch({"discovery_notes": [{"ref": "n2"}]})
        assert len(merged.discovery_notes) == 2


class TestAddArtifactVersion:
    """add_artifact_version replaces finalized artifacts with new versions."""

    def test_replace_finalized_artifact(self):
        state = _make_minimal()
        original = _make_babok_artifact(artifact_id="ba-1", title="v1", status="approved")
        state = state.merge_patch({"current_state_descriptions": [original]})
        new_version = _make_babok_artifact(artifact_id="ba-1", title="v2", status="validated")
        updated = state.add_artifact_version("current_state_descriptions", new_version)
        assert len(updated.current_state_descriptions) == 1
        assert updated.current_state_descriptions[0]["title"] == "v2"
        assert updated.current_state_descriptions[0]["status"] == "validated"

    def test_add_artifact_version_rejects_non_babok_field(self):
        state = _make_minimal()
        with pytest.raises(ValueError, match="not a BABOK artifact list"):
            state.add_artifact_version("discovery_notes", {"artifact_id": "n1"})

    def test_add_artifact_version_rejects_nonexistent_artifact_id(self):
        state = _make_minimal()
        state = state.merge_patch({"current_state_descriptions": [_make_babok_artifact(artifact_id="ba-1")]})
        with pytest.raises(ValueError, match="No existing artifact"):
            state.add_artifact_version("current_state_descriptions", _make_babok_artifact(artifact_id="ba-99"))

    def test_add_artifact_version_rejects_non_finalized(self):
        state = _make_minimal()
        draft = _make_babok_artifact(artifact_id="ba-1", status="proposed")
        state = state.merge_patch({"current_state_descriptions": [draft]})
        with pytest.raises(ValueError, match="not finalized"):
            state.add_artifact_version("current_state_descriptions", _make_babok_artifact(artifact_id="ba-1"))

    def test_add_artifact_version_updates_updated_at(self):
        state = _make_minimal()
        original = _make_babok_artifact(artifact_id="ba-1", status="approved")
        state = state.merge_patch({"current_state_descriptions": [original]})
        original_updated = state.updated_at
        new_version = _make_babok_artifact(artifact_id="ba-1", title="v2", status="validated")
        updated = state.add_artifact_version("current_state_descriptions", new_version)
        assert updated.updated_at >= original_updated

    def test_add_artifact_version_immutability(self):
        """Original state must not be mutated by add_artifact_version."""
        state = _make_minimal()
        original = _make_babok_artifact(artifact_id="ba-1", status="approved")
        state = state.merge_patch({"current_state_descriptions": [original]})
        original_count = len(state.current_state_descriptions)
        new_version = _make_babok_artifact(artifact_id="ba-1", title="v2", status="validated")
        state.add_artifact_version("current_state_descriptions", new_version)
        assert len(state.current_state_descriptions) == original_count
        assert state.current_state_descriptions[0]["title"] == "Current State Analysis"


# ---------------------------------------------------------------------------
# Serialization tests
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_round_trip_to_dict_and_back(self):
        state = _make_full(operator_goal="Test goal")
        state = state.merge_patch({
            "discovery_notes": [{"ref": "n1", "content": "test"}],
            "ontology_objects": {"Party": [{"id": "p1", "name": "Acme"}]},
        })
        d = state.model_dump()
        state2 = EngagementState.model_validate(d)
        assert state2.engagement_id == state.engagement_id
        assert state2.tenant_id == state.tenant_id
        assert state2.operator_goal == state.operator_goal
        assert state2.discovery_notes == state.discovery_notes
        assert state2.ontology_objects == state.ontology_objects

    def test_serialization_includes_all_fields(self):
        state = _make_full()
        d = state.model_dump()
        expected_keys = {
            "engagement_id", "tenant_id", "workspace_mode", "phase",
            "operator_goal", "discovery_notes", "ontology_objects",
            "ontology_links", "truth_findings", "workflow_specs",
            "executable_workflow_drafts", "planned_actions",
            "unresolved_questions", "data_sources", "freshness",
            "updated_at",
            "current_state_descriptions", "business_objectives",
            "risk_analyses", "change_strategies", "solution_evaluations",
            "agent_inbox",
        }
        assert set(d.keys()) == expected_keys

    def test_json_serialization(self):
        state = _make_minimal()
        json_str = state.model_dump_json()
        assert "engagement_id" in json_str
        assert "discovery" in json_str
        state2 = EngagementState.model_validate_json(json_str)
        assert state2.engagement_id == state.engagement_id

    def test_partial_deserialization_fails(self):
        with pytest.raises(ValidationError):
            EngagementState.model_validate({"engagement_id": "e1"})


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_discovery_notes_list(self):
        state = _make_minimal()
        assert state.discovery_notes == []

    def test_empty_string_operator_goal(self):
        state = _make_minimal(operator_goal="")
        assert state.operator_goal == ""

    def test_none_operator_goal(self):
        state = _make_minimal()
        assert state.operator_goal is None

    def test_duplicate_notes_appended(self):
        state = _make_minimal()
        note = {"ref": "n1", "content": "test"}
        state = state.merge_patch({"discovery_notes": [note]})
        state = state.merge_patch({"discovery_notes": [note]})  # same note again
        assert len(state.discovery_notes) == 2  # duplicates allowed

    def test_merge_patch_with_empty_dict(self):
        state = _make_minimal()
        merged = state.merge_patch({})
        assert merged.engagement_id == state.engagement_id
        assert merged.phase == state.phase

    def test_merge_patch_with_allowed_keys_from_constant(self):
        """All keys defined in _ALLOWED_PATCH_KEYS must be accepted."""
        state = _make_minimal()
        for key in _ALLOWED_PATCH_KEYS:
            if key == "workspace_mode":
                continue  # immutable
            if key in _BABOK_ARTIFACT_PATCH_KEYS:
                patch = {key: []}
            elif key in ("ontology_objects", "freshness"):
                patch = {key: {}}
            elif key == "phase":
                patch = {key: "discovery"}
            elif key == "operator_goal":
                patch = {key: "test"}
            elif key == "unresolved_questions":
                patch = {key: []}
            else:
                patch = {key: []}
            merged = state.merge_patch(patch)
            assert merged is not None

    def test_create_with_dashboard_mode(self):
        state = _make_minimal(workspace_mode="dashboard")
        assert state.workspace_mode == "dashboard"

    def test_freshness_provenance_multiple_merges(self):
        state = _make_minimal()
        state = state.merge_patch({"phase": "ontology_mapping"}, provenance="Discovery")
        state = state.merge_patch({"phase": "truth_analysis"}, provenance="ChiefOfStaff")
        assert "Discovery" in state.freshness
        assert "ChiefOfStaff" in state.freshness
