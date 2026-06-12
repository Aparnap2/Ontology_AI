"""Finance rules — extracted detection functions and MBA primitives.

Section 1: 17 detection functions extracted from guardian/watchlist.py lambdas.
    These are named, typed, testable counterparts of the SeedStageBlindspot
    detection_logic callables. Each takes explicit typed parameters (not a
    signals dict) and returns bool.

Section 2: 7 MBA finance primitives — deterministic calculators for burn
    multiple, runway, NPV, IRR, WACC, and working capital pressure.

Pure Python — no LangGraph, LLM, or framework imports. Standard library only.
"""

from __future__ import annotations

from src.llmops.tracer import traced

__all__ = [
    # Section 1 — Detection functions
    "is_silent_churn_death",
    "is_burn_multiple_creep",
    "is_customer_concentration_risk",
    "is_runway_compression_acceleration",
    "is_failed_payment_cluster",
    "is_payroll_revenue_breach",
    "is_leaky_bucket_activation",
    "is_power_user_mrr_masking",
    "is_feature_adoption_drop",
    "is_cohort_retention_degradation",
    "is_nrr_below_100",
    "is_trial_activation_wall",
    "is_error_segment_correlation",
    "is_support_outpacing_growth",
    "is_cross_channel_bug_convergence",
    "is_deploy_frequency_collapse",
    "is_infra_unit_economics_divergence",
    # Section 2 — MBA primitives
    "compute_burn_multiple",
    "compute_runway_days",
    "compute_effective_runway_days",
    "compute_npv",
    "compute_irr",
    "compute_wacc",
    "compute_working_capital_pressure",
]


# ═══════════════════════════════════════════════════════════════════════
# Section 1 — Extracted Detection Functions (17 total)
# ═══════════════════════════════════════════════════════════════════════

# ── Finance Detection (FG-01 to FG-06) ──────────────────────────────


def is_silent_churn_death(monthly_churn_pct: float) -> bool:
    """FG-01: Monthly churn exceeds the fatal 3% threshold.

    3% monthly churn is 36% annual churn — a death spiral most
    founders don't notice until it is too late to fix before fundraising.
    """
    return monthly_churn_pct > 0.03


def is_burn_multiple_creep(net_burn: float, net_new_arr: float) -> bool:
    """FG-02: Burn multiple exceeds 2x (spending $2 for $1 new ARR).

    Series A benchmark is < 1.5x. Above 2x is a critical red flag
    that investors calculate in the first 10 minutes of diligence.
    """
    return net_burn > 0 and net_new_arr > 0 and (net_burn / net_new_arr) > 2.0


def is_customer_concentration_risk(top_customer_mrr: float, total_mrr: float) -> bool:
    """FG-03: Single customer exceeds 30% of total MRR.

    If that customer churns, more than a third of revenue vanishes
    overnight. Diversification takes 3–6 months minimum.
    """
    return total_mrr > 0 and (top_customer_mrr / total_mrr) > 0.30


def is_runway_compression_acceleration(
    burn_rate: float, prev_burn_rate: float, runway_days: int
) -> bool:
    """FG-04: Burn is accelerating while runway is under 9 months.

    Effective runway is ~6 months after accounting for 3 months of
    fundraising prep time. Burn rate growing >20% MoM with <270 days
    runway is a critical compression signal.
    """
    return (
        prev_burn_rate > 0
        and (burn_rate / prev_burn_rate) > 1.20
        and runway_days < 270
    )


def is_failed_payment_cluster(failed_payments_7d: int) -> bool:
    """FG-05: 3+ failed payments in 7 days — involuntary churn cluster.

    Involuntary churn is typically 20–40% of total churn at seed stage
    and is almost entirely preventable with a dunning sequence.
    """
    return failed_payments_7d >= 3


def is_payroll_revenue_breach(payroll_monthly: float, mrr: float) -> bool:
    """FG-06: Payroll exceeds 60% of MRR — classic overhire signal.

    The founder hired ahead of revenue instead of behind it. MRR must
    catch up before any new headcount is added.
    """
    return mrr > 0 and (payroll_monthly / mrr) > 0.60


# ── BI Detection (BG-01 to BG-06) ───────────────────────────────────


def is_leaky_bucket_activation(
    new_signups: int, activation_rate: float, mrr_growth_pct: float
) -> bool:
    """BG-01: MRR growing but activation failing — leaky bucket.

    Acquisition spend is driving MRR growth, but users are not
    activating. These require completely different fixes than
    the MRR chart suggests.
    """
    return new_signups > 0 and activation_rate < 0.40 and mrr_growth_pct > 0


def is_power_user_mrr_masking(
    top_10pct_mrr: float,
    total_mrr: float,
    avg_mrr_new: float,
    avg_mrr_all: float,
) -> bool:
    """BG-02: Top 10% of users generate 60%+ of MRR; new customers worth less.

    Aggregate MRR growth looks healthy, but per-customer economics
    are deteriorating. Investors will find this in diligence.
    """
    if total_mrr <= 0:
        return False
    return (
        (top_10pct_mrr / total_mrr) > 0.60
        and avg_mrr_new < avg_mrr_all * 0.80
    )


def is_feature_adoption_drop(adoption_pre: float, adoption_post: float) -> bool:
    """BG-03: Feature usage dropped >30% after a deploy.

    Either the deploy broke something or the wrong thing was shipped.
    Without cohort-level tracking this is almost always invisible.
    """
    return adoption_post < adoption_pre * 0.70


def is_cohort_retention_degradation(
    recent_retention: float, prior_retention: float
) -> bool:
    """BG-04: New cohorts retain 10%+ worse than prior cohorts.

    The earliest signal of ICP drift. Blended retention masks this —
    cohort-by-cohort degradation is invisible in aggregate numbers
    until it is very bad.
    """
    return recent_retention < prior_retention * 0.90


def is_nrr_below_100(nrr: float) -> bool:
    """BG-05: Net Revenue Retention below 100%.

    NRR < 100% means the company is losing more revenue than it
    expands. Every new customer partially replaces a churned one.
    Sub-100 NRR at Series A kills term sheets.
    """
    return nrr < 100


def is_trial_activation_wall(trial_step_dropoffs: list[dict]) -> bool:
    """BG-06: >50% of trial users abandon at a single activation step.

    One specific friction point is creating an activation wall.
    Almost always solvable in one sprint once identified.
    """
    return any(step["drop_pct"] > 0.50 for step in trial_step_dropoffs)


# ── Ops Detection (OG-01 to OG-05) ──────────────────────────────────


def is_error_segment_correlation(errors_by_segment: list[dict]) -> bool:
    """OG-01: Errors concentrated in one user segment (>10%).

    Aggregate error rates hide segment-specific failures. One
    user type may be having a completely broken experience while
    the aggregate error rate looks fine.
    """
    return any(seg["error_pct"] > 0.10 for seg in errors_by_segment)


def is_support_outpacing_growth(
    support_growth_pct: float, user_growth_pct: float
) -> bool:
    """OG-02: Support volume growing 1.5x faster than users.

    The product is getting harder to use as it grows. This ratio
    is almost never tracked but reveals the trend that absolute
    support volume hides.
    """
    return support_growth_pct > user_growth_pct * 1.5


def is_cross_channel_bug_convergence(
    bug_mentions_by_channel: dict[str, int],
) -> bool:
    """OG-03: Same bug reported across 3+ channels simultaneously.

    Multi-channel bug convergence means the user base is actively
    experiencing the issue. Blast radius is larger than any single
    channel shows. Treat this as an incident.
    """
    return sum(1 for count in bug_mentions_by_channel.values() if count > 0) >= 3


def is_deploy_frequency_collapse(
    deploys_this_month: int, deploys_last_month: int
) -> bool:
    """OG-04: Deploy frequency dropped >50% month-over-month.

    The first measurable signal of technical debt paralysis.
    When it is measurable, the debt is already significant.
    """
    return (
        deploys_last_month > 0
        and deploys_this_month < deploys_last_month * 0.50
    )


def is_infra_unit_economics_divergence(
    aws_cost_growth_pct: float, user_growth_pct: float
) -> bool:
    """OG-05: AWS cost growing 2x faster than users.

    A unit-economics structural problem, not a DevOps problem.
    Usually traced to an early architectural decision (N+1 query,
    polling loop, unindexed table) that gets exponentially more
    expensive to fix at 10x users.
    """
    return aws_cost_growth_pct > user_growth_pct * 2


# ═══════════════════════════════════════════════════════════════════════
# Section 2 — MBA Finance Primitives (7 functions)
# ═══════════════════════════════════════════════════════════════════════


@traced(agent="finance_rules", signature="compute", as_type="span")
def compute_burn_multiple(net_burn: float, net_new_arr: float) -> float:
    """Net Burn / Net New ARR. Series A benchmark < 1.5x.

    Args:
        net_burn: Monthly net cash burn (positive value).
        net_new_arr: Net new annual recurring revenue added.

    Returns:
        Burn multiple ratio, or infinity if net_new_arr is zero.
    """
    if net_new_arr <= 0:
        return float("inf")
    return net_burn / net_new_arr


def compute_runway_days(bank_balance: float, monthly_burn: float) -> int:
    """Days of runway at the current burn rate.

    Args:
        bank_balance: Cash in the bank.
        monthly_burn: Monthly operating burn (positive value).

    Returns:
        Estimated days until the bank runs dry. Returns 9999 if
        monthly_burn is zero or negative (no burn).
    """
    if monthly_burn <= 0:
        return 9999
    return int((bank_balance / monthly_burn) * 30)


def compute_effective_runway_days(
    runway_days: int, fundraising_months: int = 3
) -> int:
    """Effective runway after subtracting fundraising preparation time.

    Fundraising typically consumes 3 months of a founder's focus
    and operating runway. The effective runway is total runway
    minus this prep period.

    Args:
        runway_days: Total runway days from ``compute_runway_days``.
        fundraising_months: Months needed to prepare for fundraising
            (default 3).

    Returns:
        Effective runway days, floored at 0.
    """
    return max(0, runway_days - (fundraising_months * 30))


def compute_npv(cash_flows: list[float], discount_rate: float) -> float:
    """Net Present Value — pure Python implementation.

    NPV = sum(CF_t / (1 + r)^t) for t = 0 .. n-1

    Args:
        cash_flows: List of cash flows (negative = investment outlay).
        discount_rate: Discount rate (e.g., 0.10 for 10%).

    Returns:
        Net present value.
    """
    return sum(
        cf / (1 + discount_rate) ** t
        for t, cf in enumerate(cash_flows)
    )


def compute_irr(
    cash_flows: list[float],
    tolerance: float = 1e-6,
    max_iter: int = 1000,
) -> float:
    """Internal Rate of Return via bisection method.

    IRR is the discount rate that makes NPV(cash_flows) == 0.

    Args:
        cash_flows: List of cash flows (first is typically negative).
        tolerance: Convergence threshold (default 1e-6).
        max_iter: Maximum bisection iterations (default 1000).

    Returns:
        Estimated IRR as a decimal (e.g., 0.25 for 25%).
    """
    lo, hi = -0.999, 10.0
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        npv = compute_npv(cash_flows, mid)
        if abs(npv) < tolerance:
            return mid
        if npv > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def compute_wacc(
    equity_weight: float,
    cost_of_equity: float,
    debt_weight: float,
    cost_of_debt: float,
    tax_rate: float,
) -> float:
    """Weighted Average Cost of Capital.

    WACC = E/(E+D) * Re + D/(E+D) * Rd * (1 - Tc)

    Args:
        equity_weight: Equity weight in capital structure (e.g., 0.60).
        cost_of_equity: Cost of equity (e.g., 0.15 for 15%).
        debt_weight: Debt weight in capital structure (e.g., 0.40).
        cost_of_debt: Cost of debt (e.g., 0.08 for 8%).
        tax_rate: Corporate tax rate (e.g., 0.21 for 21%).

    Returns:
        WACC as a decimal.
    """
    return round(
        equity_weight * cost_of_equity
        + debt_weight * cost_of_debt * (1 - tax_rate),
        10,
    )


def compute_working_capital_pressure(
    current_assets: float,
    current_liabilities: float,
    monthly_burn: float,
) -> dict:
    """Working capital ratio and months of buffer.

    Args:
        current_assets: Total current assets (cash, receivables, etc.).
        current_liabilities: Total current liabilities (AP, deferred rev, etc.).
        monthly_burn: Monthly operating burn.

    Returns:
        Dict with keys:
            - ratio: Current ratio (current assets / current liabilities).
            - buffer_months: Months of buffer (net working capital / burn).
            - critical: True if ratio < 1.2 or buffer < 3 months.
    """
    ratio = current_assets / max(current_liabilities, 1)
    buffer_months = (current_assets - current_liabilities) / max(monthly_burn, 1)
    return {
        "ratio": round(ratio, 2),
        "buffer_months": round(buffer_months, 1),
        "critical": ratio < 1.2 or buffer_months < 3,
    }
