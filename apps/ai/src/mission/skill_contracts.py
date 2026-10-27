"""Skill contracts — bounded, reusable units of work with typed I/O.

A skill is a single capability with predictable input/output models. It can
never schedule its own mission (no goals, no memory, no authority). Exactly 4
skills are agentic — they run a bounded internal loop (gather → reflect →
decide → synthesize) capped by ``max_iterations``.

Employees reach external systems only through :class:`SkillContext.run_capability`,
which enforces the role capability allowlist.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field

from src.entities.models import OntologyBaseModel


class SkillInput(OntologyBaseModel):
    """Base input model for every skill (tenant-scoped, extra="forbid")."""

    tenant_id: str


class SkillOutput(BaseModel):
    """Base output model for every skill.

    ``extra="allow"`` so skills (and test stubs) can emit arbitrary result
    fields without declaring every key up front.
    """

    model_config = ConfigDict(extra="allow")


class SkillDefinition(OntologyBaseModel):
    """Static metadata + runnable for one skill.

    ``extra="forbid"`` guarantees a skill has no mission-writing surface.
    """

    name: str
    description: str
    input_model: type[SkillInput]
    output_model: type[SkillOutput]
    run: Callable[["SkillContext", SkillInput], Awaitable[SkillOutput]]
    uses_llm: bool = False
    llm_calls: list[str] = Field(default_factory=list)
    capability_ops: list[str] = Field(default_factory=list)
    sub_skills: list[str] = Field(default_factory=list)
    agentic: bool = False
    max_iterations: int = 1
    allowed_roles: list[str] = Field(default_factory=list)


class SkillResult(OntologyBaseModel):
    """The result of running a skill (or an agentic skill loop)."""

    skill: str
    output: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    iterations: int = 0
    ok: bool = True
    error: str | None = None


@dataclass
class SkillContext:
    """Execution context handed to every skill run.

    ``run_capability`` is the ONLY way a skill reaches an external system —
    it routes through the capability-op registry and enforces the role
    capability allowlist.
    """

    tenant_id: str
    role: str | None = None
    role_config: Any = None
    capabilities: Any = None
    llm: Any = None

    async def run_capability(self, op: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a capability op, enforcing the role allowlist."""
        if self.capabilities is None:
            from src.mission.capability_ops import CapabilityOpRegistry

            self.capabilities = CapabilityOpRegistry
        role_caps = None
        if self.role_config is not None:
            role_caps = list(getattr(self.role_config, "capabilities", []) or [])
        return self.capabilities.execute(op, params, self.tenant_id, role_caps=role_caps)