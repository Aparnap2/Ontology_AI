"""Step runners — the seven frozen MVP control patterns.

Each runner is a focused, stateless ``async def`` that mutates a shared
:class:`RunState`.  ``_run_skill`` resolves the skill via the registry and
runs it through the :class:`SkillContext.run_capability` path.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from src.mission.plan import PlanResultStep, PlanStep, StepPattern
from src.mission.signal_handler import SignalHandler
from src.mission.skill_contracts import SkillContext, SkillDefinition
from src.mission.skill_registry import SkillRegistry
from src.mission import capability_ops
from src.mission.verify import VerifyOutcome, build_action_result, verify_write
from src.mission.employee_role_config import EmployeeRoleConfig

logger = logging.getLogger(__name__)


@dataclass
class RunState:
    """Mutable execution context shared by all step runners."""

    role: EmployeeRoleConfig
    tenant_id: str
    skill_context: SkillContext
    signal_handler: SignalHandler | None = None
    last_output: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    action_results: list[dict[str, Any]] = field(default_factory=list)
    results: list[PlanResultStep] = field(default_factory=list)
    status: str = "completed"
    stop: bool = False
    replan: bool = False
    error: str | None = None


def _ensure_skills_loaded() -> None:
    """Load canonical skills if the registry is empty (lazy, idempotent)."""
    if not SkillRegistry._skills:
        SkillRegistry.load_all()


def _build_skill_context(role: Any, tenant_id: str) -> SkillContext:
    """Build the SkillContext that routes calls through CapabilityOpRegistry."""
    return SkillContext(
        tenant_id=tenant_id,
        role=role.role_id,
        role_config=role,
        capabilities=capability_ops.CapabilityOpRegistry,
    )


async def _run_skill(step: PlanStep, state: RunState) -> dict[str, Any]:
    """Resolve and run a single skill, recording the result."""
    _ensure_skills_loaded()
    skill: SkillDefinition = SkillRegistry.get_skill(step.skill)
    SkillRegistry.assert_allowed(step.skill, state.role.skills)
    inp = skill.input_model(tenant_id=state.tenant_id)
    try:
        output = await skill.run(state.skill_context, inp)
    except Exception as exc:
        state.stop = True
        state.error = str(exc)
        state.results.append(
            PlanResultStep(
                step_id=step.id,
                pattern=step.pattern,
                skill=step.skill,
                output={},
                ok=False,
                error=str(exc),
            )
        )
        return {}
    output_dict = output.model_dump()
    state.results.append(
        PlanResultStep(
            step_id=step.id,
            pattern=step.pattern,
            skill=step.skill,
            output=output_dict,
            ok=True,
        )
    )
    state.last_output = output_dict
    return output_dict


# ── The seven frozen patterns ─────────────────────────────────────────────


async def run_sequential(step: PlanStep, state: RunState) -> None:
    """Run one skill sequentially, recording the result."""
    if step.skill:
        await _run_skill(step, state)


async def run_parallel(step: PlanStep, state: RunState) -> None:
    """Fan out concurrent skill runs and join before returning."""

    async def _one(skill_name: str) -> dict[str, Any]:
        ps = PlanStep(
            id=step.id + "/" + skill_name,
            pattern=StepPattern.SEQUENTIAL,
            skill=skill_name,
        )
        return await _run_skill(ps, state)

    results = await asyncio.gather(*[_one(s) for s in step.skills])
    for r in results:
        state.last_output = r


async def run_branch(step: PlanStep, state: RunState) -> None:
    """Select the next skill from the prior output value."""
    value = state.last_output.get(step.condition or "", "")
    chosen = step.branches.get(str(value))
    if not chosen:
        state.stop = True
        state.error = f"branch: no match for {step.condition}={value}"
        return
    ps = PlanStep(
        id=step.id + "/branch",
        pattern=StepPattern.SEQUENTIAL,
        skill=chosen,
    )
    await _run_skill(ps, state)


async def run_loop(step: PlanStep, state: RunState) -> None:
    """Repeat the skill at most ``max_iterations`` times, stopping on terminal."""
    for _ in range(step.max_iterations):
        if state.stop:
            break
        output = await _run_skill(step, state)
        if output.get("terminal"):
            break


async def run_wait(step: PlanStep, state: RunState) -> None:
    """Emit a HITL signal and suspend until the human resolves."""
    if state.signal_handler is None:
        state.stop = True
        state.error = "no signal handler registered"
        return
    payload = {
        "reason": step.params.get("reason", ""),
        "signal": step.params.get("signal", "hitl-approval"),
    }
    state.signal_handler.emit(payload["signal"], payload)
    decision = await state.signal_handler.await_decision(payload["signal"])
    if not decision.get("approved"):
        state.stop = True
        state.events.append({"type": "mission_interrupted", "decision": decision})


async def run_replan(step: PlanStep, state: RunState) -> None:
    """Re-evaluate on low confidence and emit a replanned event."""
    conf = state.last_output.get("confidence", 1.0)
    threshold = step.params.get("confidence_threshold", 0.5)
    if conf < threshold:
        state.events.append({"type": "mission_replanned", "confidence": conf})
        state.replan = True


async def run_verify(step: PlanStep, state: RunState) -> None:
    """Read-back verification: pass → continue, fail → block downstream."""
    action = step.action
    # The read-back MUST run under the same authority as the write it is
    # verifying. It previously omitted role_caps entirely and relied on the
    # capability registry treating an absent allowlist as "unrestricted",
    # so verification executed with no authority at all. Now that the
    # registry fails closed, omitting it silently denied every read-back.
    # A role that can write must be able to read, so the role's effective
    # capability allowlist is passed through unchanged.
    outcome: VerifyOutcome = await verify_write(
        action["capability"],
        action["params"],
        action["expected"],
        state.tenant_id,
        capabilities=capability_ops.CapabilityOpRegistry,
        role_caps=list(state.role.capabilities or []) or None,
    )
    ar = build_action_result(f"action-{step.id}", outcome)
    state.action_results.append(ar.model_dump())
    if not outcome.verified:
        state.stop = True


# ── Pattern dispatch map ──────────────────────────────────────────────────

RUNNERS: dict[StepPattern, Any] = {
    StepPattern.SEQUENTIAL: run_sequential,
    StepPattern.PARALLEL: run_parallel,
    StepPattern.BRANCH: run_branch,
    StepPattern.LOOP: run_loop,
    StepPattern.WAIT: run_wait,
    StepPattern.REPLAN: run_replan,
    StepPattern.VERIFY: run_verify,
}
