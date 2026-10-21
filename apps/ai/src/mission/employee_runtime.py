"""EmployeeRuntime — the shared interpreter over PlanSteps.

A single instance per mission run.  Skills are resolved from config (never
the legacy hard-coded intern classes).  The 7 pattern runners live in
``step_runners.py`` — this file is a thin dispatch loop.
"""
from __future__ import annotations

from typing import Any

from src.mission.employee_role_registry import EmployeeRoleRegistry
from src.mission.mission_config import MissionNotAllowedError, MissionSpec
from src.mission.plan import MissionRunResult, PlanStep, StepPattern
from src.mission.signal_handler import InMemorySignalHandler
from src.mission.step_runners import RUNNERS, RunState, _build_skill_context
from src.mission.skill_registry import SkillRegistry  # noqa: F401 — re-exported


def _skill_can_write(skill_name: str) -> bool:
    """True when a skill declares any non-read capability op."""
    from src.mission.capability_ops import CapabilityOpRegistry

    skill = SkillRegistry.get_skill(skill_name)
    for op_name in skill.capability_ops:
        try:
            op = CapabilityOpRegistry.get(op_name)
        except KeyError:
            continue
        if op.kind not in ("read", "search"):
            return True
    return False

__all__ = [
    "EmployeeRuntime",
    "InMemorySignalHandler",
    "PlanStep",
    "StepPattern",
    "MissionRunResult",
]


class EmployeeRuntime:
    """Shared runtime that executes one mission plan at a time."""

    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id
        self.signal_handler = InMemorySignalHandler()
        self.roles = EmployeeRoleRegistry

    def resolve_role(self, role_id: str) -> Any:
        """Return the config-driven EmployeeRoleConfig (never a legacy class)."""
        return self.roles.get_role(role_id)

    async def run_plan(
        self, plan: list[PlanStep], role: Any
    ) -> MissionRunResult:
        """Walk the plan, dispatching each step by pattern to its runner."""
        skill_ctx = _build_skill_context(role, self.tenant_id)
        state = RunState(
            role=role,
            tenant_id=self.tenant_id,
            skill_context=skill_ctx,
            signal_handler=self.signal_handler,
        )
        replan_budget = 1

        i = 0
        while i < len(plan):
            if state.stop:
                break

            step = plan[i]

            # ── Risk gate (policy_bridge) ──────────────────────────────
            if step.params.get("risk_tier"):
                from src.mission.policy_bridge import classify_risk

                tier = classify_risk(step.params, role)
                if tier in ("CRITICAL",):
                    state.status = "failed"
                    state.events.append({"type": "mission_failed", "tier": tier})
                    state.stop = True
                    break
                if tier in ("HIGH",):
                    self.signal_handler.emit(
                        "hitl-approval",
                        {"reason": "high-risk step", "tier": tier},
                    )
                    decision = await self.signal_handler.await_decision("hitl-approval")
                    if not decision.get("approved"):
                        state.stop = True
                        state.events.append(
                            {"type": "mission_interrupted", "decision": decision}
                        )
                        break

            # ── Dispatch by pattern ────────────────────────────────────
            runner = RUNNERS.get(step.pattern)
            if runner is not None:
                await runner(step, state)

            i += 1

            # ── Replan restart (bounded to 1) ─────────────────────────
            if state.replan and replan_budget > 0:
                replan_budget -= 1
                state.replan = False
                already_planned = {s.skill for s in plan if s.skill}
                extras = [
                    PlanStep(pattern=StepPattern.SEQUENTIAL, skill=s, id=f"replan/{s}")
                    for s in role.skills
                    if s not in already_planned
                ]
                plan = extras + plan
                i = 0

        return MissionRunResult(
            status=state.status,
            events=state.events,
            action_results=state.action_results,
        )

    async def run_mission(self, spec: MissionSpec) -> MissionRunResult:
        """Selection gate: verify the mission is admissible, then run it.

        Fail-closed allowlist chain: mission type ∈ role → plan ⊆ mission
        allowlist ⊆ role skills → skill capability ops ⊆ effective
        capabilities → read_only policy rejects write-capable skills.
        """
        role = self.resolve_role(spec.employee_role)
        if spec.mission_type not in role.mission_types:
            raise MissionNotAllowedError(
                f"mission {spec.id!r} type {spec.mission_type!r} not in "
                f"role {spec.employee_role} mission_types {role.mission_types}"
            )
        allowed = spec.effective_skills()
        if not set(allowed) <= set(role.skills):
            raise MissionNotAllowedError(
                f"mission {spec.id!r} allowlist {allowed} outside "
                f"role {spec.employee_role} skills"
            )
        if not set(spec.skill_plan) <= set(allowed):
            raise MissionNotAllowedError(
                f"mission {spec.id!r} plan {spec.skill_plan} outside "
                f"mission allowlist {allowed}"
            )
        effective_caps = spec.effective_capabilities(role.capabilities)
        for skill_name in spec.skill_plan:
            skill = SkillRegistry.get_skill(skill_name)
            outside = [op for op in skill.capability_ops if op not in effective_caps]
            if outside:
                raise MissionNotAllowedError(
                    f"mission {spec.id!r} skill {skill_name!r} ops {outside} "
                    f"outside effective capabilities"
                )
            if spec.approval_policy == "read_only" and _skill_can_write(skill_name):
                raise MissionNotAllowedError(
                    f"mission {spec.id!r} is read_only but skill "
                    f"{skill_name!r} is write-capable"
                )
        plan = [
            PlanStep(
                pattern=StepPattern.SEQUENTIAL,
                skill=s,
                id=str(i),
            )
            for i, s in enumerate(spec.skill_plan)
        ]
        return await self.run_plan(plan, role)
