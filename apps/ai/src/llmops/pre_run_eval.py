"""Pre-run evaluation score - gates LLM execution based on context quality."""
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class PreRunEval:
    context_quality: float
    similar_events_count: int
    graphiti_hit: bool
    mission_state_age_s: int
    eval_passed: bool
    reason: str


def evaluate_pre_run(state: dict) -> PreRunEval:
    """Evaluate pre-run conditions for LLM agent execution.
    
    Gate rule:
        eval_passed = (context_quality > 0.65 OR similar_events_count == 0) 
                      AND mission_state_age_s < 3600
    
    Args:
        state: dict with keys:
            - context_quality: float (0.0-1.0)
            - similar_events_count: int
            - graphiti_hit: bool
            - mission_state_updated_at: datetime
    
    Returns:
        PreRunEval dataclass
    """
    context_quality = state.get("context_quality", 0.0)
    similar_events_count = state.get("similar_events_count", 0)
    graphiti_hit = state.get("graphiti_hit", False)
    
    mission_state_updated_at = state.get("mission_state_updated_at")
    if mission_state_updated_at:
        mission_state_age_s = int((datetime.now(timezone.utc) - mission_state_updated_at).total_seconds())
    else:
        mission_state_age_s = 999999
    
    quality_gate = context_quality > 0.65 or similar_events_count == 0
    freshness_gate = mission_state_age_s < 3600
    eval_passed = quality_gate and freshness_gate
    
    if eval_passed:
        reason = "all gates passed"
    else:
        if mission_state_age_s >= 3600:
            reason = f"mission_state_stale:{mission_state_age_s}s"
        elif context_quality <= 0.65 and similar_events_count > 0:
            reason = "context_quality_low_similar_events_exist"
        else:
            reason = "eval_failed"
    
    return PreRunEval(
        context_quality=context_quality,
        similar_events_count=similar_events_count,
        graphiti_hit=graphiti_hit,
        mission_state_age_s=mission_state_age_s,
        eval_passed=eval_passed,
        reason=reason,
    )