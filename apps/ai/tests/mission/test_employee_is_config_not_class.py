"""The hard architectural test for V6 Milestone #3.

An Employee is a **role config** (``EmployeeRoleConfig`` loaded from YAML),
never a giant class. The runtime resolves roles from config only and must
never instantiate the legacy hard-coded intern classes in
``src/mission/employee.py``.
"""

from __future__ import annotations

from src.mission.employee import DigitalEmployee
from src.mission.employee_role_config import EmployeeRoleConfig
from src.mission.employee_role_registry import EmployeeRoleRegistry
from src.mission.employee_runtime import EmployeeRuntime


class TestEmployeeIsConfigNotClass:
    def test_adding_employee_is_config_not_class(self):
        """Adding an employee = adding a YAML entry, never a new class."""
        roles = EmployeeRoleRegistry.load()
        assert len(roles) == 3
        assert set(roles) == {"revops", "productops", "orgint"}
        # Roles are config objects, not DigitalEmployee subclasses:
        assert all(not isinstance(r, DigitalEmployee) for r in roles.values())
        assert all(isinstance(r, EmployeeRoleConfig) for r in roles.values())

    def test_runtime_never_instantiates_hardcoded_interns(self):
        """The runtime path resolves roles from config, not EMPLOYEE_REGISTRY classes."""
        runtime = EmployeeRuntime(tenant_id="t1")
        role = runtime.resolve_role("revops")
        assert isinstance(role, EmployeeRoleConfig)
        assert type(role).__name__ != "RevenueOperationsAnalyst"

    def test_no_finance_intern_and_no_fourth_pillar(self):
        """Frozen: exactly 3 employees; no finance intern, no 4th pillar."""
        assert "finance" not in EmployeeRoleRegistry.load()
        assert "finance" not in EmployeeRuntime(tenant_id="t1").roles.roles()
