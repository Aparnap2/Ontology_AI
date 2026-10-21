"""RevOps skills — the 6 frozen skills of the Revenue Operations Analyst.

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


# ── pipeline_health ────────────────────────────────────────────────────────


class PipelineHealthInput(SkillInput):
    as_of: str = ""


class PipelineHealthReport(SkillOutput):
    stage_distribution: list[dict[str, Any]] = []
    at_risk_amount: float = 0.0
    health_score: float = 0.0
    summary: str = ""


async def run_pipeline_health(
    ctx: SkillContext, inp: PipelineHealthInput
) -> PipelineHealthReport:
    deals = ctx.run_capability("salesforce.read", {"object_type": "opportunity"}).get("data", [])
    if not isinstance(deals, list):
        deals = []
    stage_distribution: dict[str, float] = {}
    total = 0.0
    for deal in deals:
        stage = str(deal.get("stage", "unknown"))
        amount = float(deal.get("amount", deal.get("value_cents", 0)) or 0)
        stage_distribution[stage] = stage_distribution.get(stage, 0.0) + amount
        total += amount
    at_risk = sum(
        amount for stage, amount in stage_distribution.items() if stage in {"negotiation", "closing"}
    )
    health_score = 1.0 - (at_risk / total) if total else 0.0
    summary = await llm_ops.summarize(
        ctx,
        f"Pipeline of {len(deals)} deals; at-risk {at_risk:.2f}; health {health_score:.2f}.",
    )
    return PipelineHealthReport(
        stage_distribution=[
            {"stage": stage, "amount": amount} for stage, amount in stage_distribution.items()
        ],
        at_risk_amount=at_risk,
        health_score=round(health_score, 3),
        summary=summary,
    )


# ── stalled_opportunity_investigation (agentic) ────────────────────────────


class StalledOpportunityInvestigationInput(SkillInput):
    max_deals: int = 10


class StalledOpportunityReport(SkillOutput):
    stalled_deals: list[dict[str, Any]] = []
    root_cause: str = ""
    next_action: str = ""
    recommendation: str = ""
    confidence: float = 0.0


class _StalledOpportunityAdapter:
    async def gather_evidence(
        self, ctx: SkillContext, inp: StalledOpportunityInvestigationInput, iteration: int
    ) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        deals = ctx.run_capability("salesforce.read", {"object_type": "opportunity"}).get(
            "data", []
        )
        if isinstance(deals, list):
            for deal in deals[: inp.max_deals]:
                evidence.append({"type": "deal", "data": deal})
        messages = ctx.run_capability(
            "slack.search", {"channel": "#sales", "query": "stalled"}
        ).get("data", [])
        if isinstance(messages, list):
            evidence.append({"type": "slack", "data": messages[:5]})
        issues = ctx.run_capability("jira.search", {"query": "stalled"}).get("data", [])
        if isinstance(issues, list):
            evidence.append({"type": "jira", "data": issues[:5]})
        return evidence

    async def reflect(
        self, ctx: SkillContext, inp: StalledOpportunityInvestigationInput, evidence: list[dict]
    ) -> dict[str, Any]:
        return await llm_ops.analyze_kpi(ctx, evidence, kpi="stall_reason")

    async def decide(
        self, ctx: SkillContext, inp: StalledOpportunityInvestigationInput, reflection: dict
    ) -> AgenticDecision:
        options = reflection.get("findings", []) or []
        decision = await llm_ops.compare_options(ctx, options, "impact")
        return AgenticDecision(
            terminal=bool(decision.get("terminal", False)),
            next_action=decision.get("selected", ""),
            reasoning=decision.get("rationale", ""),
        )

    async def synthesize(
        self,
        ctx: SkillContext,
        inp: StalledOpportunityInvestigationInput,
        evidence: list[dict],
        decision: AgenticDecision,
    ) -> StalledOpportunityReport:
        recommendation = await llm_ops.generate_recommendation(
            ctx, {"decision": decision.model_dump(), "evidence_count": len(evidence)}
        )
        return StalledOpportunityReport(
            stalled_deals=[e["data"] for e in evidence if e.get("type") == "deal"],
            root_cause=decision.reasoning,
            next_action=decision.next_action,
            recommendation=recommendation.get("action", ""),
            confidence=float(recommendation.get("confidence", 0.0) or 0.0),
        )


async def run_stalled_opportunity_investigation(
    ctx: SkillContext, inp: StalledOpportunityInvestigationInput
) -> StalledOpportunityReport:
    return await run_agentic_skill(_STALLED_SKILL, ctx, inp, _StalledOpportunityAdapter())


# ── crm_hygiene ────────────────────────────────────────────────────────────


class CRMHygieneInput(SkillInput):
    max_records: int = 50


class CRMHygieneReport(SkillOutput):
    stale_records: int = 0
    corrected_records: int = 0
    recommendation: str = ""


async def run_crm_hygiene(ctx: SkillContext, inp: CRMHygieneInput) -> CRMHygieneReport:
    deals = ctx.run_capability("salesforce.read", {"object_type": "opportunity"}).get("data", [])
    if not isinstance(deals, list):
        deals = []
    stale = [d for d in deals if not d.get("stage") or d.get("stage") == "unknown"]
    corrected = 0
    for deal in stale[: inp.max_records]:
        result = ctx.run_capability(
            "salesforce.update",
            {"record_id": deal.get("id", ""), "fields": {"stage": "discovery"}},
        )
        if result.get("ok"):
            corrected += 1
    recommendation = await llm_ops.generate_recommendation(
        ctx, {"stale": len(stale), "corrected": corrected}
    )
    return CRMHygieneReport(
        stale_records=len(stale),
        corrected_records=corrected,
        recommendation=recommendation.get("action", ""),
    )


# ── followup_analysis ──────────────────────────────────────────────────────


class FollowupAnalysisInput(SkillInput):
    channel: str = "#sales"


class FollowupAnalysisReport(SkillOutput):
    followups_needed: int = 0
    draft: str = ""


async def run_followup_analysis(
    ctx: SkillContext, inp: FollowupAnalysisInput
) -> FollowupAnalysisReport:
    deals = ctx.run_capability("salesforce.read", {"object_type": "opportunity"}).get("data", [])
    if not isinstance(deals, list):
        deals = []
    messages = ctx.run_capability(
        "slack.search", {"channel": inp.channel, "query": "follow up"}
    ).get("data", [])
    if not isinstance(messages, list):
        messages = []
    draft = await llm_ops.draft_message(
        ctx,
        "follow up on stalled deals",
        {"deals": len(deals), "recent_threads": len(messages)},
    )
    return FollowupAnalysisReport(followups_needed=len(deals), draft=draft)


# ── account_context ────────────────────────────────────────────────────────


class AccountContextInput(SkillInput):
    account_id: str = ""


class AccountContextReport(SkillOutput):
    account: dict[str, Any] = {}
    context: str = ""


async def run_account_context(ctx: SkillContext, inp: AccountContextInput) -> AccountContextReport:
    customers = ctx.run_capability("salesforce.read", {"object_type": "customer"}).get("data", [])
    if not isinstance(customers, list):
        customers = []
    account = next((c for c in customers if c.get("id") == inp.account_id), {})
    messages = ctx.run_capability(
        "slack.search", {"channel": "#sales", "query": inp.account_id}
    ).get("data", [])
    if not isinstance(messages, list):
        messages = []
    context = await llm_ops.summarize(
        ctx, f"Account {inp.account_id}: {len(messages)} recent threads."
    )
    return AccountContextReport(account=account, context=context)


# ── revenue_kpi_analysis ───────────────────────────────────────────────────


class RevenueKPIAnalysisInput(SkillInput):
    kpi: str = "forecast_accuracy"


class RevenueKPIAnalysisReport(SkillOutput):
    findings: dict[str, Any] = {}
    trend: str = ""
    confidence: float = 0.0


async def run_revenue_kpi_analysis(
    ctx: SkillContext, inp: RevenueKPIAnalysisInput
) -> RevenueKPIAnalysisReport:
    deals = ctx.run_capability("salesforce.read", {"object_type": "opportunity"}).get("data", [])
    if not isinstance(deals, list):
        deals = []
    analysis = await llm_ops.analyze_kpi(ctx, deals, kpi=inp.kpi)
    return RevenueKPIAnalysisReport(
        findings=analysis.get("findings", {}),
        trend=analysis.get("trend", ""),
        confidence=float(analysis.get("confidence", 0.0) or 0.0),
    )


# ── Registration ───────────────────────────────────────────────────────────


_STALLED_SKILL = SkillDefinition(
    name="stalled_opportunity_investigation",
    description="Investigate stalled opportunities and recommend an unblock.",
    input_model=StalledOpportunityInvestigationInput,
    output_model=StalledOpportunityReport,
    run=run_stalled_opportunity_investigation,
    uses_llm=True,
    llm_calls=["analyze_kpi", "compare_options", "generate_recommendation", "draft_message"],
    capability_ops=["salesforce.read", "slack.search", "jira.search"],
    agentic=True,
    max_iterations=3,
    allowed_roles=["revops"],
)


def register() -> None:
    """Register the 6 RevOps skills."""
    SkillRegistry.register(
        SkillDefinition(
            name="pipeline_health",
            description="Assess pipeline health and flag at-risk deals.",
            input_model=PipelineHealthInput,
            output_model=PipelineHealthReport,
            run=run_pipeline_health,
            uses_llm=True,
            llm_calls=["summarize"],
            capability_ops=["salesforce.read"],
            allowed_roles=["revops"],
        )
    )
    SkillRegistry.register(_STALLED_SKILL)
    SkillRegistry.register(
        SkillDefinition(
            name="crm_hygiene",
            description="Audit and correct stale CRM records.",
            input_model=CRMHygieneInput,
            output_model=CRMHygieneReport,
            run=run_crm_hygiene,
            uses_llm=True,
            llm_calls=["generate_recommendation"],
            capability_ops=["salesforce.read", "salesforce.update"],
            allowed_roles=["revops"],
        )
    )
    SkillRegistry.register(
        SkillDefinition(
            name="followup_analysis",
            description="Identify deals needing follow-up and draft the message.",
            input_model=FollowupAnalysisInput,
            output_model=FollowupAnalysisReport,
            run=run_followup_analysis,
            uses_llm=True,
            llm_calls=["draft_message"],
            capability_ops=["salesforce.read", "slack.search"],
            allowed_roles=["revops"],
        )
    )
    SkillRegistry.register(
        SkillDefinition(
            name="account_context",
            description="Build context for a single account.",
            input_model=AccountContextInput,
            output_model=AccountContextReport,
            run=run_account_context,
            uses_llm=True,
            llm_calls=["summarize"],
            capability_ops=["salesforce.read", "slack.search"],
            allowed_roles=["revops"],
        )
    )
    SkillRegistry.register(
        SkillDefinition(
            name="revenue_kpi_analysis",
            description="Analyze revenue KPIs against targets.",
            input_model=RevenueKPIAnalysisInput,
            output_model=RevenueKPIAnalysisReport,
            run=run_revenue_kpi_analysis,
            uses_llm=True,
            llm_calls=["analyze_kpi"],
            capability_ops=["salesforce.read"],
            allowed_roles=["revops"],
        )
    )