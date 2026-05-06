"""Guardian Watchlist — 16 seed-stage failure patterns.

Each pattern detects a specific blindspot that solo founders
typically don't know to watch for, with baked-in context about
why it matters, what happens if missed, and one concrete action.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class SeedStageBlindspot:
    id: str
    name: str
    domain: str                        # finance | bi | ops
    signals_required: list[str]
    detection_logic: Callable
    why_it_matters: str
    what_founder_doesnt_know: str
    urgency_horizon: str
    historical_precedent: str
    one_action: str
    severity: str = "warning"          # info | warning | critical


# ── Finance Guardian (FG-01 to FG-06) ──────────────────────────────

FG_01_SILENT_CHURN_DEATH = SeedStageBlindspot(
    id="FG-01", name="Silent Churn Death", domain="finance",
    signals_required=["monthly_churn_pct"],
    detection_logic=lambda s: s.get("monthly_churn_pct", 0) > 0.03,
    why_it_matters=(
        "3% monthly churn is 36% annual churn. "
        "Series A investors look at annual churn. "
        "You will not be able to explain this away."
    ),
    what_founder_doesnt_know=(
        "Monthly churn that 'seems fine' is almost always fatal "
        "at scale. Most founders realize this at month 16, not month 6."
    ),
    urgency_horizon=(
        "You have ~8 months before this is unfixable before "
        "your Series A attempt."
    ),
    historical_precedent=(
        "The typical pattern: churn starts at 2%, founders focus on "
        "acquisition, churn reaches 4%, too late to fix the root "
        "cause before fundraising."
    ),
    one_action=(
        "Call one churned customer this week. Don't ask what went "
        "wrong. Ask what they expected the product to do that it didn't."
    ),
    severity="warning",
)

FG_02_BURN_MULTIPLE_CREEP = SeedStageBlindspot(
    id="FG-02", name="Burn Multiple Creep", domain="finance",
    signals_required=["net_new_arr", "net_burn"],
    detection_logic=lambda s: (
        s.get("net_burn", 0) > 0 and
        s.get("net_new_arr", 1) > 0 and
        (s["net_burn"] / s["net_new_arr"]) > 2.0
    ),
    why_it_matters=(
        "Burn multiple > 2x: you're spending $2 to make $1 of new ARR. "
        "Series A benchmark: < 1.5x."
    ),
    what_founder_doesnt_know=(
        "Most founders track absolute burn. Almost none track burn "
        "multiple. Investors calculate it in the first 10 minutes."
    ),
    urgency_horizon="Series A investors will catch this immediately.",
    historical_precedent=(
        "High burn multiple is the most common reason founders get "
        "caught off-guard in Series A diligence."
    ),
    one_action=(
        "Calculate your burn multiple right now: net burn / net new ARR. "
        "If it's above 2, find one non-headcount cost to cut this month."
    ),
    severity="critical",
)

FG_03_CUSTOMER_CONCENTRATION = SeedStageBlindspot(
    id="FG-03", name="Customer Concentration Risk", domain="finance",
    signals_required=["top_customer_mrr", "total_mrr"],
    detection_logic=lambda s: (
        s.get("total_mrr", 0) > 0 and
        (s.get("top_customer_mrr", 0) / s["total_mrr"]) > 0.30
    ),
    why_it_matters=(
        "One customer is >30% of MRR. If they churn, you lose more "
        "than a third of revenue overnight."
    ),
    what_founder_doesnt_know=(
        "This looks fine until the day it doesn't. Investors will "
        "immediately ask what happens if that customer leaves."
    ),
    urgency_horizon="Diversification takes 3–6 months minimum. Start now.",
    historical_precedent=(
        "The most common version: the big customer was also the design "
        "partner whose requirements shaped the product in ways that "
        "don't generalize."
    ),
    one_action=(
        "Identify two prospects in your pipeline who are NOT similar "
        "to your top customer. Prioritize closing one this month."
    ),
    severity="warning",
)

FG_04_RUNWAY_COMPRESSION = SeedStageBlindspot(
    id="FG-04", name="Runway Compression Acceleration", domain="finance",
    signals_required=["burn_rate", "prev_burn_rate", "runway_days"],
    detection_logic=lambda s: (
        s.get("prev_burn_rate", 0) > 0 and
        (s.get("burn_rate", 0) / s["prev_burn_rate"]) > 1.20 and
        s.get("runway_days", 999) < 270
    ),
    why_it_matters=(
        "Burn is accelerating while runway is already under 9 months. "
        "You are compressing your fundraising window faster than you think."
    ),
    what_founder_doesnt_know=(
        "9 months runway feels long. 3 months are spent fundraising. "
        "You actually have 6 months of operating time left."
    ),
    urgency_horizon="Effective runway is ~6 months from today.",
    historical_precedent=(
        "Founders who hit this usually hired one month too early "
        "while revenue growth lagged behind plan."
    ),
    one_action="Freeze all non-essential spend for 30 days. Review every recurring charge.",
    severity="critical",
)

FG_05_FAILED_PAYMENT_CLUSTER = SeedStageBlindspot(
    id="FG-05", name="Failed Payment Cluster", domain="finance",
    signals_required=["failed_payments_7d"],
    detection_logic=lambda s: s.get("failed_payments_7d", 0) >= 3,
    why_it_matters=(
        "3+ failed payments in 7 days is involuntary churn in progress. "
        "Most of these customers won't update their card — they'll just leave."
    ),
    what_founder_doesnt_know=(
        "Involuntary churn is typically 20–40% of total churn at seed. "
        "It's almost entirely preventable with a dunning sequence."
    ),
    urgency_horizon="Every day without a dunning email loses ~30% of recoverable revenue.",
    historical_precedent=(
        "Founders discover involuntary churn in their annual review "
        "when the number is already material. It's been losing them "
        "money for months."
    ),
    one_action=(
        "Turn on Stripe's built-in Smart Retries today. "
        "Send a personal email to each failed payment customer this week."
    ),
    severity="warning",
)

FG_06_PAYROLL_REVENUE_RATIO = SeedStageBlindspot(
    id="FG-06", name="Payroll Revenue Ratio Breach", domain="finance",
    signals_required=["payroll_monthly", "mrr"],
    detection_logic=lambda s: (
        s.get("mrr", 0) > 0 and
        (s.get("payroll_monthly", 0) / s["mrr"]) > 0.60
    ),
    why_it_matters=(
        "Payroll is >60% of MRR. Classic seed-stage overhire signal. "
        "You hired ahead of revenue, not behind it."
    ),
    what_founder_doesnt_know=(
        "This ratio is invisible until burn suddenly spikes. "
        "By then, the only fix is painful."
    ),
    urgency_horizon="Hire freeze until MRR catches up to payroll trajectory.",
    historical_precedent=(
        "The most common version: founder hired a head of sales before "
        "having repeatable sales motion. Salary ran 6 months with no pipeline."
    ),
    one_action="No new hires until MRR covers current payroll at 50% ratio.",
    severity="warning",
)

# ── BI Guardian (BG-01 to BG-06) ───────────────────────────────────

BG_01_LEAKY_BUCKET = SeedStageBlindspot(
    id="BG-01", name="Leaky Bucket Activation", domain="bi",
    signals_required=["new_signups", "activation_rate", "mrr_growth_pct"],
    detection_logic=lambda s: (
        s.get("new_signups", 0) > 0 and
        s.get("activation_rate", 1) < 0.40 and
        s.get("mrr_growth_pct", 0) > 0
    ),
    why_it_matters=(
        "MRR is growing but activation is failing. You are buying growth "
        "with acquisition spend while leaking users before they see value."
    ),
    what_founder_doesnt_know=(
        "A growing MRR number masks an activation wall. "
        "The acquisition channel is working. The product is not. "
        "These require completely different fixes."
    ),
    urgency_horizon="Every week of delayed fix costs more CAC payback time.",
    historical_precedent=(
        "Founders who hit this discover it when they try to scale paid "
        "acquisition and unit economics collapse."
    ),
    one_action=(
        "Watch 3 session recordings of users who signed up and never "
        "activated. Find the drop-off step. Fix that one thing."
    ),
    severity="warning",
)

BG_02_POWER_USER_MASKING = SeedStageBlindspot(
    id="BG-02", name="Power User MRR Masking", domain="bi",
    signals_required=["top_10pct_mrr", "total_mrr",
                      "avg_mrr_new_customers", "avg_mrr_all_customers"],
    detection_logic=lambda s: (
        s.get("top_10pct_mrr", 0) / max(s.get("total_mrr", 1), 1) > 0.60 and
        s.get("avg_mrr_new_customers", 0) <
        s.get("avg_mrr_all_customers", 1) * 0.80
    ),
    why_it_matters=(
        "Your top 10% of users generate 60%+ of MRR. "
        "New customers are worth materially less. "
        "Your growth story is weaker than your MRR chart shows."
    ),
    what_founder_doesnt_know=(
        "Aggregate MRR growth looks healthy. Per-customer economics "
        "are deteriorating. Investors will find this in diligence."
    ),
    urgency_horizon="This compounds with every lower-value customer you add.",
    historical_precedent=(
        "Founders present MRR growth charts to investors. "
        "Investors ask for MRR per customer over time. "
        "The conversation gets uncomfortable."
    ),
    one_action="Segment your MRR by cohort month. Calculate average MRR per customer for each cohort.",
    severity="warning",
)

BG_03_FEATURE_DROP = SeedStageBlindspot(
    id="BG-03", name="Feature Adoption Post-Deploy Drop", domain="bi",
    signals_required=["feature_name", "adoption_pre_deploy", "adoption_post_deploy"],
    detection_logic=lambda s: (
        s.get("adoption_post_deploy", 1) <
        s.get("adoption_pre_deploy", 0) * 0.70
    ),
    why_it_matters=(
        "You shipped something and usage dropped. "
        "Either you broke something, or you shipped the wrong thing."
    ),
    what_founder_doesnt_know=(
        "Feature adoption drop after deploy is almost always invisible "
        "without cohort-level tracking. Founders assume the deploy worked."
    ),
    urgency_horizon="Every week of delay means more users habituating to the broken state.",
    historical_precedent=(
        "Founders find out about this during user interviews, "
        "weeks after the deploy, when the damage is done."
    ),
    one_action="Talk to one user who used this feature before the deploy and hasn't since.",
    severity="warning",
)

BG_04_COHORT_RETENTION = SeedStageBlindspot(
    id="BG-04", name="Cohort Retention Degradation", domain="bi",
    signals_required=["cohort_retention_30d_recent", "cohort_retention_30d_prior"],
    detection_logic=lambda s: (
        s.get("cohort_retention_30d_recent", 1) <
        s.get("cohort_retention_30d_prior", 0) * 0.90
    ),
    why_it_matters=(
        "New cohorts are retaining 10%+ worse than prior cohorts. "
        "PMF is not holding as you grow. "
        "This is the earliest signal of ICP drift."
    ),
    what_founder_doesnt_know=(
        "Most founders look at blended retention. "
        "Cohort-by-cohort degradation is invisible in aggregate numbers "
        "until it's very bad."
    ),
    urgency_horizon="ICP drift is reversible early. Almost impossible to reverse late.",
    historical_precedent=(
        "Early customers self-selected perfectly. Newer customers came "
        "from broader acquisition. The product doesn't fit as well. "
        "Founders realize this when they're already 3 cohorts deep."
    ),
    one_action=(
        "Interview 2 customers from your most recent cohort. "
        "Find one thing different about how they use the product vs. early customers."
    ),
    severity="critical",
)

BG_05_NRR_BELOW_100 = SeedStageBlindspot(
    id="BG-05", name="NRR Below 100 at Seed", domain="bi",
    signals_required=["nrr"],
    detection_logic=lambda s: s.get("nrr", 100) < 100,
    why_it_matters=(
        "NRR < 100% means you're losing more than you're expanding. "
        "You have no land-and-expand motion. "
        "Every new customer partially replaces a churned one."
    ),
    what_founder_doesnt_know=(
        "NRR below 100% at seed is fixable. NRR below 100% "
        "presented at Series A is a red flag that's hard to explain away."
    ),
    urgency_horizon="Fix the expansion motion before fundraising.",
    historical_precedent=(
        "Founders pitch growth by acquisition. Investors ask about "
        "NRR. Sub-100 NRR with no explanation kills term sheets."
    ),
    one_action=(
        "Identify one upsell or expansion trigger in your product. "
        "Build the Slack alert or email for it this week."
    ),
    severity="critical",
)

BG_06_TRIAL_WALL = SeedStageBlindspot(
    id="BG-06", name="Trial Activation Wall", domain="bi",
    signals_required=["trial_step_dropoffs"],
    detection_logic=lambda s: (
        any(step["drop_pct"] > 0.50 for step in
            s.get("trial_step_dropoffs", []))
    ),
    why_it_matters=(
        "More than 50% of trial users are abandoning at one specific step. "
        "You have an activation wall, not a funnel."
    ),
    what_founder_doesnt_know=(
        "Activation walls are rarely obvious. Founders assume users "
        "drop off for general reasons. The wall is almost always one "
        "specific friction point."
    ),
    urgency_horizon="Every day this exists, you're wasting your acquisition spend.",
    historical_precedent=(
        "Almost always solvable in one sprint once identified. "
        "Founders who track it improve trial-to-paid 2–3x in 30 days."
    ),
    one_action="Watch 5 session recordings of users who hit that step and bounced.",
    severity="warning",
)

# ── Ops Guardian (OG-01 to OG-05) ──────────────────────────────────

OG_01_ERROR_SEGMENT = SeedStageBlindspot(
    id="OG-01", name="Error Rate User Segment Correlation", domain="ops",
    signals_required=["errors_by_segment"],
    detection_logic=lambda s: (
        any(seg["error_pct"] > 0.10 for seg in
            s.get("errors_by_segment", []))
    ),
    why_it_matters=(
        "Errors are concentrated in one user segment. "
        "This isn't random noise — it's a systematic failure "
        "for a specific type of user."
    ),
    what_founder_doesnt_know=(
        "Aggregate error rates hide segment-specific failures. "
        "One user type might be having a completely broken experience "
        "while your aggregate error rate looks fine."
    ),
    urgency_horizon="Every hour this runs, that user segment loses trust.",
    historical_precedent=(
        "This is usually traced to a missing edge case for a specific "
        "plan tier, geography, or usage pattern."
    ),
    one_action="Identify the segment. Find one user in it. Ask them what's broken.",
    severity="warning",
)

OG_02_SUPPORT_GROWTH = SeedStageBlindspot(
    id="OG-02", name="Support Volume Outpacing Growth", domain="ops",
    signals_required=["support_tickets_growth_pct", "user_growth_pct"],
    detection_logic=lambda s: (
        s.get("support_tickets_growth_pct", 0) >
        s.get("user_growth_pct", 0) * 1.5
    ),
    why_it_matters=(
        "Support is growing 1.5x faster than users. "
        "Your product is getting harder to use as it grows, not easier."
    ),
    what_founder_doesnt_know=(
        "This ratio is almost never tracked. Founders track absolute "
        "support volume, not relative to users. "
        "The ratio reveals the trend."
    ),
    urgency_horizon="At scale, this ratio makes you unsupportable.",
    historical_precedent=(
        "Usually caused by accumulating UX debt that founders "
        "deprioritize in favor of new features."
    ),
    one_action=(
        "Find the top 3 support ticket categories this month. "
        "Pick one. Add it to next sprint as a product fix, not a support response."
    ),
    severity="warning",
)

OG_03_CROSS_CHANNEL_BUG = SeedStageBlindspot(
    id="OG-03", name="Cross-Channel Bug Convergence", domain="ops",
    signals_required=["bug_mentions_by_channel"],
    detection_logic=lambda s: (
        sum(1 for ch in s.get("bug_mentions_by_channel", {}).values()
            if ch > 0) >= 3
    ),
    why_it_matters=(
        "The same bug is being reported across 3+ channels simultaneously. "
        "This is no longer an edge case. It's a product incident."
    ),
    what_founder_doesnt_know=(
        "Multi-channel bug convergence means your user base is actively "
        "experiencing the issue. The blast radius is larger than any "
        "single channel shows."
    ),
    urgency_horizon="Treat this as an incident. Drop what you're doing.",
    historical_precedent=(
        "Founders who miss cross-channel convergence find out "
        "when a user posts publicly. By then it's a reputation problem."
    ),
    one_action="Stop. Fix this now. Post a status update in Slack to users.",
    severity="critical",
)

OG_04_DEPLOY_COLLAPSE = SeedStageBlindspot(
    id="OG-04", name="Deploy Frequency Collapse", domain="ops",
    signals_required=["deploys_this_month", "deploys_last_month"],
    detection_logic=lambda s: (
        "deploys_this_month" in s and  # Signal must exist (not defaulted)
        "deploys_last_month" in s and  # Signal must exist (not defaulted)
        s.get("deploys_last_month", 1) > 0 and
        s.get("deploys_this_month", 0) <
        s.get("deploys_last_month", 1) * 0.50
    ),
    why_it_matters=(
        "Deploy frequency dropped >50% MoM. "
        "This is almost always the first measurable signal of "
        "technical debt paralysis."
    ),
    what_founder_doesnt_know=(
        "Founders feel the slowdown subjectively but rarely measure it. "
        "When it's measurable, the debt is already significant."
    ),
    urgency_horizon="Technical debt compounds. The longer this runs, the worse it gets.",
    historical_precedent=(
        "Founders at month 18 wish they had spent one sprint on "
        "test coverage at month 6. They never find time to go back."
    ),
    one_action="Schedule a 1-week debt sprint in the next 30 days. Don't ship features that week. Just clean.",
    severity="warning",
)

OG_05_INFRA_UNIT_ECON = SeedStageBlindspot(
    id="OG-05", name="Infrastructure Unit Economics Divergence",
    domain="ops",
    signals_required=["aws_cost_growth_pct", "user_growth_pct"],
    detection_logic=lambda s: (
        s.get("aws_cost_growth_pct", 0) >
        s.get("user_growth_pct", 0) * 2
    ),
    why_it_matters=(
        "AWS is growing 2x faster than users. "
        "You have a unit economics structural problem, not a DevOps problem."
    ),
    what_founder_doesnt_know=(
        "Easy to dismiss as 'we'll optimize later.' The pattern "
        "usually indicates an architectural decision that gets harder "
        "to fix the longer you wait."
    ),
    urgency_horizon="Cheapest to fix now. Exponentially expensive at 10x users.",
    historical_precedent=(
        "Almost always traced to a specific architectural choice made "
        "in the first 90 days. Usually an N+1 query, a polling loop, "
        "or an unindexed table."
    ),
    one_action=(
        "You built this. You know where to look. "
        "Run EXPLAIN ANALYZE on your three most frequent queries this week."
    ),
    severity="warning",
)

# ── Master list ─────────────────────────────────────────────────────

SEED_STAGE_WATCHLIST: list[SeedStageBlindspot] = [
    # Finance (6)
    FG_01_SILENT_CHURN_DEATH,
    FG_02_BURN_MULTIPLE_CREEP,
    FG_03_CUSTOMER_CONCENTRATION,
    FG_04_RUNWAY_COMPRESSION,
    FG_05_FAILED_PAYMENT_CLUSTER,
    FG_06_PAYROLL_REVENUE_RATIO,
    # BI (6)
    BG_01_LEAKY_BUCKET,
    BG_02_POWER_USER_MASKING,
    BG_03_FEATURE_DROP,
    BG_04_COHORT_RETENTION,
    BG_05_NRR_BELOW_100,
    BG_06_TRIAL_WALL,
    # Ops (5)
    OG_01_ERROR_SEGMENT,
    OG_02_SUPPORT_GROWTH,
    OG_03_CROSS_CHANNEL_BUG,
    OG_04_DEPLOY_COLLAPSE,
    OG_05_INFRA_UNIT_ECON,
]
