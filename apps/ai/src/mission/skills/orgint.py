"""OrgIntelligence skills — the 6 frozen skills of the Organizational Intelligence Analyst.

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


# ── decision_capture (agentic) ─────────────────────────────────────────────


class DecisionCaptureInput(SkillInput):
    channel: str = "#leadership"
    max_threads: int = 10


class DecisionCaptureReport(SkillOutput):
    decisions: list[dict[str, Any]] = []
    captured_to: str = ""
    draft: str = ""


class _DecisionCaptureAdapter:
    async def gather_evidence(
        self, ctx: SkillContext, inp: DecisionCaptureInput, iteration: int
    ) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        messages = ctx.run_capability(
            "slack.search", {"channel": inp.channel, "query": "decided"}
        ).get("data", [])
        if isinstance(messages, list):
            for message in messages[: inp.max_threads]:
                evidence.append({"type": "message", "data": message})
        pages = ctx.run_capability("notion.read", {"query": "decisions"}).get("data", [])
        if isinstance(pages, list):
            evidence.append({"type": "notion", "data": pages[:5]})
        return evidence

    async def reflect(
        self, ctx: SkillContext, inp: DecisionCaptureInput, evidence: list[dict]
    ) -> dict[str, Any]:
        return await llm_ops.summarize(
            ctx, f"Extract decisions from {len(evidence)} evidence items."
        )

    async def decide(
        self, ctx: SkillContext, inp: DecisionCaptureInput, reflection: dict
    ) -> AgenticDecision:
        return AgenticDecision(
            terminal=True,
            next_action="capture",
            reasoning=reflection,
        )

    async def synthesize(
        self,
        ctx: SkillContext,
        inp: DecisionCaptureInput,
        evidence: list[dict],
        decision: AgenticDecision,
    ) -> DecisionCaptureReport:
        decisions = [e["data"] for e in evidence if e.get("type") == "message"]
        draft = await llm_ops.draft_message(
            ctx, "summarize captured decisions", {"count": len(decisions)}
        )
        captured_to = ""
        if decisions:
            result = ctx.run_capability(
                "notion.update",
                {"page_id": "decisions", "data": {"decisions": decisions}},
            )
            if result.get("ok"):
                captured_to = "decisions"
        return DecisionCaptureReport(
            decisions=decisions, captured_to=captured_to, draft=draft
        )


async def run_decision_capture(
    ctx: SkillContext, inp: DecisionCaptureInput
) -> DecisionCaptureReport:
    return await run_agentic_skill(_DECISION_CAPTURE_SKILL, ctx, inp, _DecisionCaptureAdapter())


# ── knowledge_gap_detection ────────────────────────────────────────────────


class KnowledgeGapDetectionInput(SkillInput):
    domain: str = "general"


class KnowledgeGapDetectionReport(SkillOutput):
    gaps: list[dict[str, Any]] = []
    summary: str = ""


async def run_knowledge_gap_detection(
    ctx: SkillContext, inp: KnowledgeGapDetectionInput
) -> KnowledgeGapDetectionReport:
    pages = ctx.run_capability("notion.read", {"query": inp.domain}).get("data", [])
    if not isinstance(pages, list):
        pages = []
    issues = ctx.run_capability("jira.read", {"jql": "labels = docs"}).get("data", [])
    if not isinstance(issues, list):
        issues = []
    gaps = [{"page": p.get("id"), "missing": "ownership"} for p in pages if not p.get("owner")]
    summary = await llm_ops.summarize(
        ctx, f"Knowledge gaps in {inp.domain}: {len(gaps)}."
    )
    return KnowledgeGapDetectionReport(gaps=gaps, summary=summary)


# ── sop_freshness ──────────────────────────────────────────────────────────


class SOPFreshnessInput(SkillInput):
    max_sops: int = 20


class SOPFreshnessReport(SkillOutput):
    stale_sops: list[dict[str, Any]] = []
    summary: str = ""


async def run_sop_freshness(ctx: SkillContext, inp: SOPFreshnessInput) -> SOPFreshnessReport:
    pages = ctx.run_capability("notion.read", {"query": "SOP"}).get("data", [])
    if not isinstance(pages, list):
        pages = []
    stale = [p for p in pages[: inp.max_sops] if not p.get("updated_at")]
    summary = await llm_ops.summarize(ctx, f"{len(stale)} stale SOPs of {len(pages)}.")
    return SOPFreshnessReport(stale_sops=stale, summary=summary)


# ── ownership_gap_detection (deterministic, no LLM) ────────────────────────


class OwnershipGapDetectionInput(SkillInput):
    max_pages: int = 50


class OwnershipGapDetectionReport(SkillOutput):
    unowned_pages: list[dict[str, Any]] = []
    total_pages: int = 0


async def run_ownership_gap_detection(
    ctx: SkillContext, inp: OwnershipGapDetectionInput
) -> OwnershipGapDetectionReport:
    pages = ctx.run_capability("notion.read", {"query": ""}).get("data", [])
    if not isinstance(pages, list):
        pages = []
    unowned = [p for p in pages[: inp.max_pages] if not p.get("owner")]
    return OwnershipGapDetectionReport(unowned_pages=unowned, total_pages=len(pages))


# ── cross_functional_investigation (agentic) ───────────────────────────────


class CrossFunctionalInvestigationInput(SkillInput):
    topic: str = ""


class CrossFunctionalInvestigationReport(SkillOutput):
    findings: list[dict[str, Any]] = []
    recommendation: str = ""
    draft: str = ""
    confidence: float = 0.0


class _CrossFunctionalAdapter:
    async def gather_evidence(
        self, ctx: SkillContext, inp: CrossFunctionalInvestigationInput, iteration: int
    ) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        messages = ctx.run_capability(
            "slack.search", {"channel": "#general", "query": inp.topic}
        ).get("data", [])
        if isinstance(messages, list):
            evidence.append({"type": "slack", "data": messages[:5]})
        issues = ctx.run_capability(
            "jira.read", {"jql": f"text ~ {inp.topic}"}
        ).get("data", [])
        if isinstance(issues, list):
            evidence.append({"type": "jira", "data": issues[:5]})
        pages = ctx.run_capability("notion.read", {"query": inp.topic}).get("data", [])
        if isinstance(pages, list):
            evidence.append({"type": "notion", "data": pages[:5]})
        return evidence

    async def reflect(
        self, ctx: SkillContext, inp: CrossFunctionalInvestigationInput, evidence: list[dict]
    ) -> dict[str, Any]:
        return await llm_ops.analyze_kpi(ctx, evidence, kpi="cross_functional_impact")

    async def decide(
        self, ctx: SkillContext, inp: CrossFunctionalInvestigationInput, reflection: dict
    ) -> AgenticDecision:
        return AgenticDecision(
            terminal=True,
            next_action="synthesize",
            reasoning=reflection.get("trend", ""),
        )

    async def synthesize(
        self,
        ctx: SkillContext,
        inp: CrossFunctionalInvestigationInput,
        evidence: list[dict],
        decision: AgenticDecision,
    ) -> CrossFunctionalInvestigationReport:
        recommendation = await llm_ops.generate_recommendation(
            ctx, {"topic": inp.topic, "evidence_count": len(evidence)}
        )
        draft = await llm_ops.draft_message(
            ctx, "cross-functional findings", {"topic": inp.topic}
        )
        return CrossFunctionalInvestigationReport(
            findings=evidence,
            recommendation=recommendation.get("action", ""),
            draft=draft,
            confidence=float(recommendation.get("confidence", 0.0) or 0.0),
        )


async def run_cross_functional_investigation(
    ctx: SkillContext, inp: CrossFunctionalInvestigationInput
) -> CrossFunctionalInvestigationReport:
    return await run_agentic_skill(
        _CROSS_FUNCTIONAL_SKILL, ctx, inp, _CrossFunctionalAdapter()
    )


# ── organizational_brief ───────────────────────────────────────────────────


class OrganizationalBriefInput(SkillInput):
    focus: str = ""


class OrganizationalBriefOutput(SkillOutput):
    brief: str = ""


async def run_organizational_brief(
    ctx: SkillContext, inp: OrganizationalBriefInput
) -> OrganizationalBriefOutput:
    messages = ctx.run_capability(
        "slack.search", {"channel": "#general", "query": inp.focus}
    ).get("data", [])
    if not isinstance(messages, list):
        messages = []
    pages = ctx.run_capability("notion.read", {"query": inp.focus}).get("data", [])
    if not isinstance(pages, list):
        pages = []
    brief = await llm_ops.organizational_brief(
        ctx, {"focus": inp.focus, "threads": len(messages), "pages": len(pages)}
    )
    return OrganizationalBriefOutput(brief=brief)


# ── Registration ───────────────────────────────────────────────────────────


_DECISION_CAPTURE_SKILL = SkillDefinition(
    name="decision_capture",
    description="Capture decisions from conversations into the knowledge base.",
    input_model=DecisionCaptureInput,
    output_model=DecisionCaptureReport,
    run=run_decision_capture,
    uses_llm=True,
    llm_calls=["summarize", "draft_message"],
    capability_ops=["slack.search", "notion.read", "notion.update"],
    agentic=True,
    max_iterations=2,
    allowed_roles=["orgint"],
)

_CROSS_FUNCTIONAL_SKILL = SkillDefinition(
    name="cross_functional_investigation",
    description="Investigate a topic across teams and synthesize findings.",
    input_model=CrossFunctionalInvestigationInput,
    output_model=CrossFunctionalInvestigationReport,
    run=run_cross_functional_investigation,
    uses_llm=True,
    llm_calls=["analyze_kpi", "generate_recommendation", "draft_message"],
    capability_ops=["slack.search", "jira.read", "notion.read"],
    agentic=True,
    max_iterations=2,
    allowed_roles=["orgint"],
)


def register() -> None:
    """Register the 6 OrgIntelligence skills."""
    SkillRegistry.register(_DECISION_CAPTURE_SKILL)
    SkillRegistry.register(
        SkillDefinition(
            name="knowledge_gap_detection",
            description="Detect knowledge gaps in a domain.",
            input_model=KnowledgeGapDetectionInput,
            output_model=KnowledgeGapDetectionReport,
            run=run_knowledge_gap_detection,
            uses_llm=True,
            llm_calls=["summarize"],
            capability_ops=["notion.read", "jira.read"],
            sub_skills=["retrieve_memory"],
            allowed_roles=["orgint"],
        )
    )
    SkillRegistry.register(
        SkillDefinition(
            name="sop_freshness",
            description="Flag stale SOPs.",
            input_model=SOPFreshnessInput,
            output_model=SOPFreshnessReport,
            run=run_sop_freshness,
            uses_llm=True,
            llm_calls=["summarize"],
            capability_ops=["notion.read"],
            allowed_roles=["orgint"],
        )
    )
    SkillRegistry.register(
        SkillDefinition(
            name="ownership_gap_detection",
            description="Find pages without an owner (deterministic).",
            input_model=OwnershipGapDetectionInput,
            output_model=OwnershipGapDetectionReport,
            run=run_ownership_gap_detection,
            uses_llm=False,
            llm_calls=[],
            capability_ops=["notion.read"],
            allowed_roles=["orgint"],
        )
    )
    SkillRegistry.register(_CROSS_FUNCTIONAL_SKILL)
    SkillRegistry.register(
        SkillDefinition(
            name="organizational_brief",
            description="Compose an organizational brief for the founder.",
            input_model=OrganizationalBriefInput,
            output_model=OrganizationalBriefOutput,
            run=run_organizational_brief,
            uses_llm=True,
            llm_calls=["organizational_brief"],
            capability_ops=["slack.search", "notion.read"],
            allowed_roles=["orgint"],
        )
    )