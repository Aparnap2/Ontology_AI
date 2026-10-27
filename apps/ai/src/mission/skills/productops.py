"""ProductOps skills — the 6 frozen skills of the Product Operations Analyst.

All external access goes through ``ctx.run_capability`` (capability ops only,
never connectors). All generation goes through ``llm_ops`` (config LLM layer).
"""
from __future__ import annotations

from typing import Any

from src.mission.agentic_loop import AgenticDecision, run_agentic_skill
from src.mission.skill_contracts import (
    SkillContext,
    SkillDefinition,
    SkillInput,
    SkillOutput,
)
from src.mission.skill_registry import SkillRegistry
from src.mission.skills import llm_ops


# ── blocked_work_investigation (agentic) ───────────────────────────────────


class BlockedWorkInvestigationInput(SkillInput):
    max_issues: int = 10


class BlockedWorkReport(SkillOutput):
    blocked_issues: list[dict[str, Any]] = []
    blocker: str = ""
    next_action: str = ""
    recommendation: str = ""
    confidence: float = 0.0


class _BlockedWorkAdapter:
    async def gather_evidence(
        self, ctx: SkillContext, inp: BlockedWorkInvestigationInput, iteration: int
    ) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        issues = ctx.run_capability(
            "jira.read", {"jql": "status = Blocked"}
        ).get("data", [])
        if isinstance(issues, list):
            for issue in issues[: inp.max_issues]:
                evidence.append({"type": "issue", "data": issue})
        messages = ctx.run_capability(
            "slack.search", {"channel": "#eng", "query": "blocked"}
        ).get("data", [])
        if isinstance(messages, list):
            evidence.append({"type": "slack", "data": messages[:5]})
        return evidence

    async def reflect(
        self, ctx: SkillContext, inp: BlockedWorkInvestigationInput, evidence: list[dict]
    ) -> dict[str, Any]:
        return await llm_ops.analyze_kpi(ctx, evidence, kpi="blocker")

    async def decide(
        self, ctx: SkillContext, inp: BlockedWorkInvestigationInput, reflection: dict
    ) -> AgenticDecision:
        options = reflection.get("findings", []) or []
        decision = await llm_ops.compare_options(ctx, options, "unblock_impact")
        return AgenticDecision(
            terminal=bool(decision.get("terminal", False)),
            next_action=decision.get("selected", ""),
            reasoning=decision.get("rationale", ""),
        )

    async def synthesize(
        self,
        ctx: SkillContext,
        inp: BlockedWorkInvestigationInput,
        evidence: list[dict],
        decision: AgenticDecision,
    ) -> BlockedWorkReport:
        recommendation = await llm_ops.generate_recommendation(
            ctx, {"decision": decision.model_dump(), "evidence_count": len(evidence)}
        )
        return BlockedWorkReport(
            blocked_issues=[e["data"] for e in evidence if e.get("type") == "issue"],
            blocker=decision.reasoning,
            next_action=decision.next_action,
            recommendation=recommendation.get("action", ""),
            confidence=float(recommendation.get("confidence", 0.0) or 0.0),
        )


async def run_blocked_work_investigation(
    ctx: SkillContext, inp: BlockedWorkInvestigationInput
) -> BlockedWorkReport:
    return await run_agentic_skill(_BLOCKED_SKILL, ctx, inp, _BlockedWorkAdapter())


# ── roadmap_health ─────────────────────────────────────────────────────────


class RoadmapHealthInput(SkillInput):
    project: str = ""


class RoadmapHealthReport(SkillOutput):
    open_epics: int = 0
    overdue_epics: int = 0
    summary: str = ""


async def run_roadmap_health(ctx: SkillContext, inp: RoadmapHealthInput) -> RoadmapHealthReport:
    issues = ctx.run_capability(
        "jira.read", {"jql": f"issuetype = Epic AND project = {inp.project}"}
    ).get("data", [])
    if not isinstance(issues, list):
        issues = []
    overdue = [i for i in issues if i.get("status") not in {"Done", "Closed"}]
    summary = await llm_ops.summarize(
        ctx, f"Roadmap: {len(issues)} epics, {len(overdue)} not done."
    )
    return RoadmapHealthReport(
        open_epics=len(issues), overdue_epics=len(overdue), summary=summary
    )


# ── sprint_health (deterministic, no LLM) ──────────────────────────────────


class SprintHealthInput(SkillInput):
    sprint: str = ""


class SprintHealthReport(SkillOutput):
    total_issues: int = 0
    completed: int = 0
    completion_rate: float = 0.0


async def run_sprint_health(ctx: SkillContext, inp: SprintHealthInput) -> SprintHealthReport:
    issues = ctx.run_capability(
        "jira.read", {"jql": f"sprint = {inp.sprint}"}
    ).get("data", [])
    if not isinstance(issues, list):
        issues = []
    completed = sum(1 for i in issues if i.get("status") in {"Done", "Closed"})
    rate = (completed / len(issues)) if issues else 0.0
    return SprintHealthReport(
        total_issues=len(issues),
        completed=completed,
        completion_rate=round(rate, 3),
    )


# ── process_adherence ──────────────────────────────────────────────────────


class ProcessAdherenceInput(SkillInput):
    process: str = ""


class ProcessAdherenceReport(SkillOutput):
    deviations: int = 0
    summary: str = ""
    recommendation: str = ""


async def run_process_adherence(
    ctx: SkillContext, inp: ProcessAdherenceInput
) -> ProcessAdherenceReport:
    issues = ctx.run_capability(
        "jira.read", {"jql": f"labels = {inp.process}"}
    ).get("data", [])
    if not isinstance(issues, list):
        issues = []
    pages = ctx.run_capability("notion.read", {"query": inp.process}).get("data", [])
    if not isinstance(pages, list):
        pages = []
    deviations = sum(1 for i in issues if not i.get("labels"))
    summary = await llm_ops.summarize(
        ctx, f"Process {inp.process}: {deviations} deviations across {len(issues)} issues."
    )
    recommendation = await llm_ops.generate_recommendation(
        ctx, {"process": inp.process, "deviations": deviations}
    )
    return ProcessAdherenceReport(
        deviations=deviations,
        summary=summary,
        recommendation=recommendation.get("action", ""),
    )


# ── documentation_sync ─────────────────────────────────────────────────────


class DocumentationSyncInput(SkillInput):
    page_id: str = ""


class DocumentationSyncReport(SkillOutput):
    drift_found: int = 0
    updated: bool = False
    draft: str = ""


async def run_documentation_sync(
    ctx: SkillContext, inp: DocumentationSyncInput
) -> DocumentationSyncReport:
    issues = ctx.run_capability("jira.read", {"jql": "updated >= -7d"}).get("data", [])
    if not isinstance(issues, list):
        issues = []
    pages = ctx.run_capability("notion.read", {"page_id": inp.page_id}).get("data", [])
    if not isinstance(pages, list):
        pages = []
    draft = await llm_ops.draft_message(
        ctx, "sync documentation with recent work", {"issues": len(issues)}
    )
    updated = False
    if inp.page_id:
        result = ctx.run_capability(
            "notion.update", {"page_id": inp.page_id, "data": {"content": draft}}
        )
        updated = bool(result.get("ok"))
    return DocumentationSyncReport(drift_found=len(issues), updated=updated, draft=draft)


# ── delivery_risk_analysis ─────────────────────────────────────────────────


class DeliveryRiskAnalysisInput(SkillInput):
    horizon_days: int = 14


class DeliveryRiskAnalysisReport(SkillOutput):
    at_risk_issues: int = 0
    recommendation: str = ""


async def run_delivery_risk_analysis(
    ctx: SkillContext, inp: DeliveryRiskAnalysisInput
) -> DeliveryRiskAnalysisReport:
    issues = ctx.run_capability(
        "jira.read", {"jql": "duedate <= now()+14d AND status != Done"}
    ).get("data", [])
    if not isinstance(issues, list):
        issues = []
    recommendation = await llm_ops.generate_recommendation(
        ctx, {"at_risk": len(issues), "horizon_days": inp.horizon_days}
    )
    return DeliveryRiskAnalysisReport(
        at_risk_issues=len(issues),
        recommendation=recommendation.get("action", ""),
    )


# ── Registration ───────────────────────────────────────────────────────────


_BLOCKED_SKILL = SkillDefinition(
    name="blocked_work_investigation",
    description="Investigate blocked engineering work and recommend an unblock.",
    input_model=BlockedWorkInvestigationInput,
    output_model=BlockedWorkReport,
    run=run_blocked_work_investigation,
    uses_llm=True,
    llm_calls=["analyze_kpi", "compare_options", "draft_message"],
    capability_ops=["jira.read", "slack.search"],
    agentic=True,
    max_iterations=3,
    allowed_roles=["productops"],
)


def register() -> None:
    """Register the 6 ProductOps skills."""
    SkillRegistry.register(_BLOCKED_SKILL)
    SkillRegistry.register(
        SkillDefinition(
            name="roadmap_health",
            description="Assess roadmap health from epics.",
            input_model=RoadmapHealthInput,
            output_model=RoadmapHealthReport,
            run=run_roadmap_health,
            uses_llm=True,
            llm_calls=["summarize"],
            capability_ops=["jira.read"],
            allowed_roles=["productops"],
        )
    )
    SkillRegistry.register(
        SkillDefinition(
            name="sprint_health",
            description="Score sprint completion deterministically.",
            input_model=SprintHealthInput,
            output_model=SprintHealthReport,
            run=run_sprint_health,
            uses_llm=False,
            llm_calls=[],
            capability_ops=["jira.read"],
            allowed_roles=["productops"],
        )
    )
    SkillRegistry.register(
        SkillDefinition(
            name="process_adherence",
            description="Detect process deviations and recommend fixes.",
            input_model=ProcessAdherenceInput,
            output_model=ProcessAdherenceReport,
            run=run_process_adherence,
            uses_llm=True,
            llm_calls=["summarize", "generate_recommendation"],
            capability_ops=["jira.read", "notion.read"],
            allowed_roles=["productops"],
        )
    )
    SkillRegistry.register(
        SkillDefinition(
            name="documentation_sync",
            description="Sync documentation with recent work.",
            input_model=DocumentationSyncInput,
            output_model=DocumentationSyncReport,
            run=run_documentation_sync,
            uses_llm=True,
            llm_calls=["draft_message"],
            capability_ops=["jira.read", "notion.read", "notion.update"],
            allowed_roles=["productops"],
        )
    )
    SkillRegistry.register(
        SkillDefinition(
            name="delivery_risk_analysis",
            description="Flag delivery risk within a horizon.",
            input_model=DeliveryRiskAnalysisInput,
            output_model=DeliveryRiskAnalysisReport,
            run=run_delivery_risk_analysis,
            uses_llm=True,
            llm_calls=["generate_recommendation"],
            capability_ops=["jira.read"],
            allowed_roles=["productops"],
        )
    )