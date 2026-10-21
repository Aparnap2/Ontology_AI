"""SkillRegistry tests — registry load, unknown-skill error, allowlist enforcement."""

from __future__ import annotations

import pytest

from src.mission.skill_contracts import SkillDefinition, SkillInput, SkillOutput
from src.mission.skill_registry import (
    SkillNotAllowedError,
    SkillNotFoundError,
    SkillRegistry,
)


class _In(SkillInput):
    """Minimal stub input model."""


class _Out(SkillOutput):
    """Minimal stub output model."""


def _stub(name: str) -> SkillDefinition:
    async def run(ctx, inp) -> _Out:
        return _Out()

    return SkillDefinition(
        name=name,
        description=name,
        input_model=_In,
        output_model=_Out,
        run=run,
        uses_llm=False,
        capability_ops=[],
        agentic=False,
    )


class TestSkillRegistry:
    def test_get_skill_known(self):
        """load_all registers the 20 real skills; get_skill returns one."""
        SkillRegistry.load_all()
        skill = SkillRegistry.get_skill("pipeline_health")
        assert skill.name == "pipeline_health"
        assert skill.description

    def test_unknown_skill_raises(self):
        """An unregistered skill name raises SkillNotFoundError."""
        with pytest.raises(SkillNotFoundError):
            SkillRegistry.get_skill("no_such_skill")

    def test_allowlist_enforcement_raises_skill_not_allowed(self):
        """assert_allowed enforces the role skill allowlist."""
        SkillRegistry.assert_allowed("pipeline_health", ["pipeline_health"])
        with pytest.raises(SkillNotAllowedError):
            SkillRegistry.assert_allowed("pipeline_health", ["crm_hygiene"])

    def test_register_adds_skill(self):
        """Registering a skill makes it visible to list_skills/get_skill."""
        SkillRegistry.register(_stub("stub-registered-skill"))
        try:
            assert "stub-registered-skill" in SkillRegistry.list_skills()
            assert SkillRegistry.get_skill("stub-registered-skill").name == (
                "stub-registered-skill"
            )
        finally:
            SkillRegistry._skills.pop("stub-registered-skill", None)

    def test_load_all_is_idempotent(self):
        """load_all can be called repeatedly without duplicating skills."""
        SkillRegistry.load_all()
        SkillRegistry.load_all()
        assert len(SkillRegistry.list_skills()) == len(set(SkillRegistry.list_skills()))