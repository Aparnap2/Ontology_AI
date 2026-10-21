"""EmployeeRoleRegistry — loads the frozen role configs from config/employees.yaml.

Adding an employee = adding a YAML entry, never a new class. The registry
follows the ``config_module`` env-template pattern: the file is located via a
search path, ``${VAR}`` placeholders are expanded from the environment, and
every role is validated as an :class:`EmployeeRoleConfig` (extra="forbid",
allowlist-validated) before it is admitted.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

from src.mission.employee_role_config import EmployeeRoleConfig

logger = logging.getLogger(__name__)


class RoleNotFoundError(KeyError):
    """Raised when a role_id is not present in the loaded config."""


def _find_config(path: str | None = None) -> Path:
    """Locate config/employees.yaml (explicit path or search path)."""
    if path:
        candidate = Path(path)
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"employees config not found: {path}")
    candidates = [
        Path.cwd() / "config" / "employees.yaml",
        Path(__file__).resolve().parents[2] / "config" / "employees.yaml",
        Path(__file__).resolve().parents[1] / "config" / "employees.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("config/employees.yaml not found on any search path")


def _load_text(path: Path) -> str:
    """Read the file and expand ${VAR} environment placeholders."""
    text = path.read_text(encoding="utf-8")
    return os.path.expandvars(text)


class EmployeeRoleRegistry:
    """Frozen registry of the three canonical employee role configs."""

    _roles: dict[str, EmployeeRoleConfig] = {}
    _loaded: bool = False

    @classmethod
    def load(cls, path: str | None = None) -> dict[str, EmployeeRoleConfig]:
        """Load (once) and return {role_id: EmployeeRoleConfig}."""
        if cls._loaded and path is None:
            return dict(cls._roles)

        config_path = _find_config(path)
        data = yaml.safe_load(_load_text(config_path)) or {}
        raw_roles: dict = data.get("roles", {})
        roles: dict[str, EmployeeRoleConfig] = {}
        for role_id, raw in raw_roles.items():
            cfg_raw = dict(raw or {})
            cfg_raw.setdefault("role_id", role_id)
            roles[role_id] = EmployeeRoleConfig(**cfg_raw)

        if not roles:
            raise ValueError(f"employees.yaml at {config_path} contained no roles")

        cls._roles = roles
        cls._loaded = True
        logger.info("Loaded %d employee role configs from %s", len(roles), config_path)
        return dict(cls._roles)

    @classmethod
    def get_role(cls, role_id: str) -> EmployeeRoleConfig:
        """Return the config for *role_id*, raising :class:`RoleNotFoundError`."""
        if not cls._loaded:
            cls.load()
        try:
            return cls._roles[role_id]
        except KeyError:
            raise RoleNotFoundError(
                f"unknown employee role {role_id!r}; loaded: {sorted(cls._roles)}"
            ) from None

    @classmethod
    def roles(cls) -> dict[str, EmployeeRoleConfig]:
        """Return a copy of the loaded role configs."""
        if not cls._loaded:
            cls.load()
        return dict(cls._roles)