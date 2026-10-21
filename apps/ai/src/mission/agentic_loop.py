"""Agentic skill loop — a bounded gather → reflect → decide → synthesize cycle.

Exactly 4 skills are agentic. They do NOT get goals, memory, or authority —
they run a bounded internal loop capped by ``skill.max_iterations`` and then
synthesize a single typed output. This is a primitive of the shared
EmployeeRuntime, not a generic workflow engine.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

from src.entities.models import OntologyBaseModel
from src.mission.skill_contracts import SkillContext, SkillDefinition, SkillResult

logger = logging.getLogger(__name__)


class AgenticDecision(OntologyBaseModel):
    """The decide step's output — whether to keep looping and what to do next."""

    terminal: bool = False
    next_action: str = ""
    reasoning: str = ""


class AgenticSkillAdapter(Protocol):
    """The four-step adapter every agentic skill implements."""

    async def gather_evidence(
        self, ctx: SkillContext, inp: Any, iteration: int
    ) -> list[dict[str, Any]]: ...

    async def reflect(
        self, ctx: SkillContext, inp: Any, evidence: list[dict[str, Any]]
    ) -> dict[str, Any]: ...

    async def decide(
        self, ctx: SkillContext, inp: Any, reflection: dict[str, Any]
    ) -> AgenticDecision: ...

    async def synthesize(
        self,
        ctx: SkillContext,
        inp: Any,
        evidence: list[dict[str, Any]],
        decision: AgenticDecision,
    ) -> Any: ...


async def run_agentic_skill(
    skill: SkillDefinition,
    ctx: SkillContext,
    inp: Any,
    adapter: AgenticSkillAdapter,
) -> SkillResult:
    """Run the bounded agentic loop for *skill* using *adapter*.

    The loop terminates when the adapter decides ``terminal`` or when
    ``max_iterations`` is exhausted — never unbounded.
    """
    budget = max(1, skill.max_iterations)
    evidence: list[dict[str, Any]] = []
    decision = AgenticDecision()
    iterations = 0

    while budget > 0 and not decision.terminal:
        try:
            evidence.extend(await adapter.gather_evidence(ctx, inp, iterations))
            reflection = await adapter.reflect(ctx, inp, evidence)
            decision = await adapter.decide(ctx, inp, reflection)
        except Exception as exc:  # noqa: BLE001 — bounded loop must not hang
            logger.exception("agentic skill %s failed at iteration %d", skill.name, iterations)
            return SkillResult(
                skill=skill.name,
                output={},
                evidence_refs=[],
                iterations=iterations,
                ok=False,
                error=str(exc),
            )
        budget -= 1
        iterations += 1

    output = await adapter.synthesize(ctx, inp, evidence, decision)
    return SkillResult(
        skill=skill.name,
        output=output.model_dump(mode="json") if hasattr(output, "model_dump") else dict(output),
        evidence_refs=[f"{skill.name}:{i}" for i in range(len(evidence))],
        iterations=iterations,
        ok=True,
    )