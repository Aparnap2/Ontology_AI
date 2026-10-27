"""Skills package — the canonical 20 skills (18 frozen + 2 RAG).

``register_all()`` prunes the registry to exactly the canonical set and
re-registers it, so ``SkillRegistry.load_all()`` is deterministic and
idempotent even if test stubs leaked in.
"""
from __future__ import annotations

from src.mission.skill_registry import SkillRegistry
from src.mission.skills import llm_ops  # noqa: F401 — primitives used by skills
from src.mission.skills import memory_skills, orgint, productops, revops

__all__ = [
    "llm_ops",
    "revops",
    "productops",
    "orgint",
    "memory_skills",
    "register_all",
]


def register_all() -> None:
    """Prune to the canonical 20 skills and register them (idempotent)."""
    SkillRegistry._skills.clear()
    revops.register()
    productops.register()
    orgint.register()
    memory_skills.register()