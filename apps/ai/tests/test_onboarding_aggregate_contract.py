"""RED contract: Onboarding is the first-class aggregate (Mission is not).

Expected to FAIL until `Onboarding` exists in src/ontology/object_types.py
with fields: customer, stakeholders, requirements, tasks, issues,
missions (M1-M6 refs), lifecycle_state — and `Mission.onboarding_id` FK.
"""
import pytest
from pydantic import ValidationError

from src.ontology.object_types import OBJECT_TYPES, Mission, Onboarding

REQUIRED_FIELDS = {
    "customer",
    "stakeholders",
    "requirements",
    "tasks",
    "issues",
    "missions",
    "lifecycle_state",
}


class TestOnboardingAggregateContract:
    def test_onboarding_registered_in_object_types(self):
        # Arrange / Act
        registered = OBJECT_TYPES.get("Onboarding")
        # Assert
        assert registered is Onboarding

    def test_onboarding_has_aggregate_fields(self):
        # Arrange
        fields = set(Onboarding.model_fields)
        # Act / Assert
        assert REQUIRED_FIELDS <= fields

    def test_onboarding_holds_m1_to_m6_mission_refs(self):
        # Arrange
        refs = [f"M{i}" for i in range(1, 7)]
        # Act
        ob = Onboarding(
            id="ob-1", customer="cust-1", stakeholders=["s-1"],
            requirements=["r-1"], tasks=["t-1"], issues=[],
            missions=refs, lifecycle_state="active",
        )
        # Assert
        assert len(ob.missions) == 6

    def test_mission_has_onboarding_fk(self):
        # Arrange / Act
        fields = set(Mission.model_fields)
        # Assert
        assert "onboarding_id" in fields

    def test_mission_is_not_the_aggregate(self):
        # Arrange / Act
        mission_fields = set(Mission.model_fields)
        onboarding_fields = set(Onboarding.model_fields)
        # Assert — aggregate-only fields live on Onboarding, never Mission
        assert "missions" not in mission_fields
        assert "customer" not in mission_fields
        assert "missions" in onboarding_fields

    def test_models_reject_extra_fields(self):
        # Arrange / Act / Assert
        assert Onboarding.model_config.get("extra") == "forbid"
        with pytest.raises(ValidationError):
            Onboarding(
                id="ob-9", customer="c", stakeholders=[], requirements=[],
                tasks=[], issues=[], missions=[], lifecycle_state="active",
                unknown_field="boom",
            )
