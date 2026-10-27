"""EmployeeRoleConfig — an Employee is a role config, never a class.

V6 Milestone #3: the three employees (RevOps, ProductOps, OrgIntelligence)
are frozen YAML inventories loaded into :class:`EmployeeRoleConfig` objects.
The runtime resolves roles from config only and never instantiates the legacy
hard-coded intern classes in ``src/mission/employee.py``.

Config and state are strictly separated:
- :meth:`EmployeeRoleConfig.to_definition` projects config fields onto the
  frozen ``EmployeeDefinition`` entity (no run state).
- :meth:`EmployeeRoleConfig.to_run` seeds an idle ``EmployeeRun`` (no config
  fields).
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from src.entities.models import EmployeeDefinition, EmployeeRun, OntologyBaseModel

RISK_TIERS = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class EmployeeRoleConfig(OntologyBaseModel):
    """Static configuration of an AI employee role.

    ``extra="forbid"`` (inherited from :class:`OntologyBaseModel`) rejects any
    unknown field, so a role can never silently carry config the runtime does
    not understand. Capability allowlists are validated against the frozen
    capability-op registry at construction time.
    """

    role_id: str
    role: str
    goals: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    policies: list[str] = Field(default_factory=list)
    authority: dict[str, Any] = Field(default_factory=dict)
    risk_threshold: RISK_TIERS = "MEDIUM"
    kpis: list[str] = Field(default_factory=list)
    memory_namespace: str = ""
    mission_types: list[str] = Field(default_factory=list)
    tenant_scope: str = ""
    persona: str = ""
    prompt_templates: dict[str, str] = Field(default_factory=dict)
    skill_tool_map: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_allowlists(self) -> "EmployeeRoleConfig":
        """Allowlist discipline: unique skills/caps, caps within the frozen ops."""
        if len(set(self.skills)) != len(self.skills):
            raise ValueError(f"role {self.role_id}: skills must be unique")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError(f"role {self.role_id}: capabilities must be unique")

        # Lazy import to avoid an import cycle at module load time.
        from src.mission.capability_ops import CapabilityOpRegistry

        known_ops = set(CapabilityOpRegistry.list_ops())
        unknown = [c for c in self.capabilities if c not in known_ops]
        if unknown:
            raise ValueError(
                f"role {self.role_id}: unknown capability ops {unknown} "
                f"(known: {sorted(known_ops)})"
            )
        return self

    # ── Config → entity projections ────────────────────────────────────────

    def to_definition(self, tenant_id: str) -> EmployeeDefinition:
        """Project every config field onto the frozen EmployeeDefinition."""
        return EmployeeDefinition(
            id=f"empdef-{self.role_id}",
            tenant_id=tenant_id,
            role=self.role,
            goals=self.goals,
            skills=self.skills,
            capabilities=self.capabilities,
            permissions=self.permissions,
            policies=self.policies,
            authority=self.authority,
            risk_threshold=self.risk_threshold,
            kpis=self.kpis,
            memory_namespace=self.memory_namespace,
            mission_types=self.mission_types,
        )

    def to_run(self, tenant_id: str) -> EmployeeRun:
        """Seed an idle EmployeeRun linked to this role's definition."""
        return EmployeeRun(
            id=f"emprun-{self.role_id}",
            tenant_id=tenant_id,
            employee_definition_id=f"empdef-{self.role_id}",
            role=self.role,
            status="idle",
            current_mission_id=None,
            active_mission_ids=[],
            memory_state={},
        )