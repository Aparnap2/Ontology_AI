"""Plan schema — pure data types for the EmployeeRuntime control loop.

A plan is a list of :class:`PlanStep` values. The shared interpreter in
``employee_runtime`` walks the plan and dispatches each step by pattern to the
runners in ``step_runners``. This module contains schema only — no execution.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from src.entities.models import OntologyBaseModel


class StepPattern(str, Enum):
    """The seven frozen MVP control patterns.

    Delegate and Reflect are behavior within the loop, not separate patterns.
    """

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    BRANCH = "branch"
    LOOP = "loop"
    WAIT = "wait"
    REPLAN = "replan"
    VERIFY = "verify"


class PlanStep(OntologyBaseModel):
    """One step in a mission plan (extra="forbid" inherited)."""

    id: str
    pattern: StepPattern
    skill: str | None = None
    skills: list[str] = []
    params: dict[str, Any] = {}
    condition: str | None = None
    branches: dict[str, str] = {}
    action: dict[str, Any] = {}
    max_iterations: int = 1
    requires_approval: bool = False


class PlanResultStep(OntologyBaseModel):
    """The outcome of executing one step."""

    step_id: str
    pattern: StepPattern
    skill: str | None = None
    output: dict[str, Any] = {}
    ok: bool = True
    error: str | None = None


class MissionRunResult(OntologyBaseModel):
    """The aggregate result of running a plan against one mission."""

    status: str = "completed"
    events: list[dict[str, Any]] = []
    action_results: list[dict[str, Any]] = []
