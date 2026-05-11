"""Data Quality Gate - runs before every agent as a LangGraph node."""
from dataclasses import dataclass
from datetime import datetime, timezone
from src.session.mission_state import MissionState


@dataclass
class DataQualityResult:
    passed: bool
    tenant_id: str
    agent_domain: str
    checks_failed: list[str]
    data_age_s: int
    reason: str


def run_data_quality_gate(state: MissionState) -> MissionState:
    """Run data quality checks before agent execution.

    Checks:
    - Data freshness (data older than 2h is stale)
    - Numeric sanity (no negatives where impossible)
    - Required fields (MRR required for finance agent)

    If data quality fails: log to Langfuse (not implemented), skip agent, no Slack alert.
    """
    checks_failed = []
    age = 0

    if state.data_last_synced:
        age = int((datetime.now(timezone.utc) - state.data_last_synced).total_seconds())
        if age > 7200:
            checks_failed.append(f"data_stale:{age}s")

    if state.runway_days is not None and state.runway_days < 0:
        checks_failed.append("runway_negative:data_corruption")

    if state.burn_rate is not None and state.burn_rate < 0:
        checks_failed.append("burn_negative:data_corruption")

    if state.churn_rate is not None and state.churn_rate > 1.0:
        checks_failed.append("churn_rate_over_100pct:impossible")

    if state.mrr is None:
        checks_failed.append("mrr_missing:required")

    result = DataQualityResult(
        passed=len(checks_failed) == 0,
        tenant_id=state.tenant_id,
        agent_domain="pre_gate",
        checks_failed=checks_failed,
        data_age_s=age,
        reason=", ".join(checks_failed) if checks_failed else "all checks passed"
    )

    state.data_quality = result

    if not result.passed:
        state.skip_reason = f"data_quality_gate_failed: {result.reason}"

    return state