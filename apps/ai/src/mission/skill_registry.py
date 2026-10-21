"""SkillRegistry — the canonical 20-skill registry.

``load_all()`` prunes the registry to exactly the canonical 20 skills (clears
then re-registers via ``src.mission.skills.register_all``), so the registry is
deterministic even if test stubs leaked in. The runtime lazy-loads only when
the registry is empty, so pre-registered stubs survive inside a test.
"""
from __future__ import annotations

import logging

from src.mission.skill_contracts import SkillDefinition

logger = logging.getLogger(__name__)


class SkillNotFoundError(Exception):
    """Raised when a skill name is not registered."""


class SkillNotAllowedError(Exception):
    """Raised when a role's skill allowlist does not admit a skill."""


class SkillRegistry:
    """Registry of the canonical 20 skills (18 frozen + 2 RAG)."""

    _skills: dict[str, SkillDefinition] = {}

    @classmethod
    def load_all(cls) -> None:
        """Prune to the canonical 20 skills and register them (idempotent)."""
        from src.mission.skills import register_all

        register_all()

    @classmethod
    def register(cls, skill: SkillDefinition) -> None:
        """Register a skill (overwrites any existing skill with the same name)."""
        cls._skills[skill.name] = skill

    @classmethod
    def get_skill(cls, name: str) -> SkillDefinition:
        """Return the skill for *name*, raising :class:`SkillNotFoundError`."""
        try:
            return cls._skills[name]
        except KeyError:
            raise SkillNotFoundError(f"unknown skill: {name}") from None

    @classmethod
    def list_skills(cls) -> list[str]:
        """Return the names of all registered skills."""
        return sorted(cls._skills)

    @classmethod
    def assert_allowed(cls, name: str, role_skills: list[str] | None) -> None:
        """Enforce the role skill allowlist (no-op when role_skills is None)."""
        if role_skills is None:
            return
        if name not in role_skills:
            raise SkillNotAllowedError(
                f"skill {name} not in role skill allowlist {role_skills}"
            )