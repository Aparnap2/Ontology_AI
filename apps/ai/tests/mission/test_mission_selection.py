"""Mission selection tests — config-driven mission → employee → skill plan.

A mission is a business objective assigned to exactly one employee whose
``mission_types`` allowlist admits it. The mission's default skill plan must
be a subset of the owning employee's skill allowlist. The full canonical set
of 10 missions lands in Milestone #4; #3 ships the config plumbing plus the
minimal set the tests need.
"""

from __future__ import annotations

import pytest

from src.mission.employee_role_registry import EmployeeRoleRegistry
from src.mission.employee_runtime import EmployeeRuntime
from src.mission.mission_config import (
    MissionNotAllowedError,
    MissionRegistry,
    MissionSpec,
)


class TestMissionSelection:
    def test_canonical_missions_load(self):
        """All missions in config/missions.yaml load as validated MissionSpecs."""
        missions = MissionRegistry.canonical_missions()
        assert len(missions) >= 6, "milestone #3 ships a minimal set; full 10 land in #4"
        for spec in missions:
            assert isinstance(spec, MissionSpec)
            assert spec.id
            assert spec.title
            assert spec.employee_role
            assert spec.mission_type
            assert spec.priority in {"low", "medium", "high", "urgent"}

    def test_each_mission_assigns_to_allowed_employee(self):
        """Every mission's mission_type is within its employee's mission_types."""
        for spec in MissionRegistry.canonical_missions():
            role = EmployeeRoleRegistry.get_role(spec.employee_role)
            assert spec.mission_type in role.mission_types, (
                f"{spec.id}: {spec.mission_type} not allowed for {spec.employee_role}"
            )

    def test_mission_skill_plan_is_allowlisted(self):
        """Every mission's default skill plan is a subset of the employee's skills."""
        for spec in MissionRegistry.canonical_missions():
            role = EmployeeRoleRegistry.get_role(spec.employee_role)
            assert set(spec.skill_plan) <= set(role.skills), (
                f"{spec.id}: plan {spec.skill_plan} outside {role.role_id} allowlist"
            )

    async def test_mission_type_not_in_role_mission_types_rejected(self):
        """A mission whose type is outside the employee's allowlist is rejected."""
        runtime = EmployeeRuntime(tenant_id="t1")
        bad = MissionSpec(
            id="m-bad",
            title="Bad mission",
            description="",
            employee_role="revops",
            mission_type="sprint_health_review",  # productops-only type
            priority="low",
            kpi_ids=[],
            skill_plan=["pipeline_health"],
        )
        with pytest.raises(MissionNotAllowedError):
            await runtime.run_mission(bad)

    def test_mission_registry_get(self):
        """get() returns the loaded MissionSpec for a known mission id."""
        spec = MissionRegistry.canonical_missions()[0]
        assert MissionRegistry.get(spec.id).id == spec.id

    def test_mission_registry_get_unknown_raises(self):
        """get() raises for an unknown mission id."""
        with pytest.raises(KeyError):
            MissionRegistry.get("m-does-not-exist")