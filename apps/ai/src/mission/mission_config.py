"""Mission config — a mission is a business objective assigned to one employee.

Missions load from ``config/missions.yaml`` as validated :class:`MissionSpec`
objects. A mission's ``mission_type`` must be within the owning employee's
``mission_types`` allowlist and its default skill plan must be a subset of the
employee's skill allowlist (enforced by the runtime at selection time).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from src.entities.models import OntologyBaseModel

logger = logging.getLogger(__name__)


class MissionNotAllowedError(KeyError):
    """Raised when a mission is not admissible for its employee role."""


class MissionSpec(OntologyBaseModel):
    """A validated mission definition from config/missions.yaml.

    Only ``id``/``title``/``employee_role``/``mission_type`` are required;
    every D2 field carries a default so existing configs load unchanged.
    An empty ``allowed_skills`` inherits ``skill_plan``; empty
    ``allowed_capabilities`` inherits the owning role's allowlist.
    """

    id: str
    title: str
    description: str = ""
    employee_role: str
    mission_type: str
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    kpi_ids: list[str] = Field(default_factory=list)
    skill_plan: list[str] = Field(default_factory=list)
    trigger_types: list[str] = Field(default_factory=list)
    goal: str = ""
    required_context: list[str] = Field(default_factory=list)
    allowed_skills: list[str] = Field(default_factory=list)
    allowed_capabilities: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    action_constraints: list[str] = Field(default_factory=list)
    approval_policy: Literal["auto", "approval_required", "read_only"] = "auto"

    def effective_skills(self) -> list[str]:
        """Skills this mission may run (explicit allowlist, else the plan)."""
        return list(self.allowed_skills) if self.allowed_skills else list(self.skill_plan)

    def effective_capabilities(self, role_capabilities: list[str]) -> list[str]:
        """Capability allowlist (explicit, else inherited from the role)."""
        return (
            list(self.allowed_capabilities)
            if self.allowed_capabilities
            else list(role_capabilities)
        )

    def missing_context(self, provided: dict[str, object]) -> list[str]:
        """Required context keys absent from *provided* (fail-closed input)."""
        return [key for key in self.required_context if key not in provided]


def _find_config(path: str | None = None) -> Path:
    """Locate config/missions.yaml (explicit path or search path)."""
    if path:
        candidate = Path(path)
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"missions config not found: {path}")
    candidates = [
        Path.cwd() / "config" / "missions.yaml",
        Path(__file__).resolve().parents[2] / "config" / "missions.yaml",
        Path(__file__).resolve().parents[1] / "config" / "missions.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("config/missions.yaml not found on any search path")


def _load_text(path: Path) -> str:
    """Read the file and expand ${VAR} environment placeholders."""
    return os.path.expandvars(path.read_text(encoding="utf-8"))


class MissionRegistry:
    """Registry of canonical missions loaded from config/missions.yaml."""

    _missions: dict[str, MissionSpec] = {}
    _loaded: bool = False

    @classmethod
    def load(cls, path: str | None = None) -> dict[str, MissionSpec]:
        """Load (once) and return {mission_id: MissionSpec}."""
        if cls._loaded and path is None:
            return dict(cls._missions)

        config_path = _find_config(path)
        data = yaml.safe_load(_load_text(config_path)) or {}
        missions: dict[str, MissionSpec] = {}
        for raw in data.get("missions", []):
            spec = MissionSpec(**raw)
            missions[spec.id] = spec

        if not missions:
            raise ValueError(f"missions.yaml at {config_path} contained no missions")

        cls._missions = missions
        cls._loaded = True
        logger.info("Loaded %d missions from %s", len(missions), config_path)
        return dict(cls._missions)

    @classmethod
    def get(cls, mission_id: str) -> MissionSpec:
        """Return the spec for *mission_id*, raising :class:`MissionNotFoundError`."""
        if not cls._loaded:
            cls.load()
        try:
            return cls._missions[mission_id]
        except KeyError:
            raise MissionNotAllowedError(
                f"unknown mission {mission_id!r}; loaded: {sorted(cls._missions)}"
            ) from None

    @classmethod
    def canonical_missions(cls) -> list[MissionSpec]:
        """Return the loaded canonical missions as a list."""
        if not cls._loaded:
            cls.load()
        return list(cls._missions.values())

    @classmethod
    def for_trigger(cls, event_type: str) -> list[MissionSpec]:
        """Return specs whose ``trigger_types`` admit *event_type*."""
        if not cls._loaded:
            cls.load()
        return [spec for spec in cls._missions.values() if event_type in spec.trigger_types]