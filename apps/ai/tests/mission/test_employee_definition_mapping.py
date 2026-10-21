"""EmployeeRoleConfig → frozen EmployeeDefinition/EmployeeRun mapping tests.

Config and state are strictly separated: ``EmployeeDefinition`` (config)
never carries run state; ``EmployeeRun`` (state) never carries config fields.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.entities.models import EmployeeDefinition, EmployeeRun
from src.mission.employee_role_config import EmployeeRoleConfig
from src.mission.employee_role_registry import EmployeeRoleRegistry


class TestEmployeeDefinitionMapping:
    def test_to_definition_projects_config_fields(self):
        """to_definition projects every config field onto EmployeeDefinition."""
        cfg = EmployeeRoleRegistry.load()["revops"]
        definition = cfg.to_definition(tenant_id="t1")

        assert isinstance(definition, EmployeeDefinition)
        assert definition.id == "empdef-revops"
        assert definition.tenant_id == "t1"
        assert definition.role == cfg.role
        assert definition.goals == cfg.goals
        assert definition.skills == cfg.skills
        assert definition.capabilities == cfg.capabilities
        assert definition.permissions == cfg.permissions
        assert definition.policies == cfg.policies
        assert definition.authority == cfg.authority
        assert definition.risk_threshold == cfg.risk_threshold
        assert definition.kpis == cfg.kpis
        assert definition.memory_namespace == cfg.memory_namespace
        assert definition.mission_types == cfg.mission_types

    def test_definition_has_no_run_state(self):
        """EmployeeDefinition (config) rejects run-state fields."""
        with pytest.raises(ValidationError):
            EmployeeDefinition(
                id="empdef-revops",
                tenant_id="t1",
                role="RevOps",
                current_mission_id="m-1",  # run state — must be rejected
            )

    def test_run_has_no_config_fields(self):
        """EmployeeRun (state) rejects config-only fields."""
        with pytest.raises(ValidationError):
            EmployeeRun(
                id="emprun-revops",
                tenant_id="t1",
                employee_definition_id="empdef-revops",
                role="RevOps",
                persona="you are revops",  # config-only — must be rejected
            )

    def test_to_run_seeds_idle_state(self):
        """to_run seeds an idle EmployeeRun linked to the definition."""
        cfg = EmployeeRoleRegistry.load()["orgint"]
        run = cfg.to_run(tenant_id="t1")

        assert isinstance(run, EmployeeRun)
        assert run.id == "emprun-orgint"
        assert run.tenant_id == "t1"
        assert run.employee_definition_id == "empdef-orgint"
        assert run.role == cfg.role
        assert run.status == "idle"
        assert run.current_mission_id is None
        assert run.active_mission_ids == []
        assert run.memory_state == {}