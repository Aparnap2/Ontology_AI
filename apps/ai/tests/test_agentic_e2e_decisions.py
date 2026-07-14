"""Part 3: Decision Making — HITL Routing + Accuracy (Agentic E2E)."""
import sys
sys.path.insert(0, "/home/aparna/Desktop/iterate_swarm/apps/ai")

from src.hitl.manager import HITLManager
from src.hitl.confidence import score_confidence
from src.agents.tools import (
    get_tools_for_tier,
    get_tools_for_pattern,
    get_tools_for_patterns,
    TOOL_REGISTRY,
)
from src.agents.tools.pause_payment_retry import tool_def as pause_tool
from src.agents.tools.flag_churn_risk import tool_def as flag_tool
from src.agents.tools.schedule_customer_checkin import tool_def as checkin_tool
from src.agents.tools.draft_investor_update import tool_def as draft_tool
from src.session.relevance_gate import evaluate_relevance, RelevanceDecision


def test_01_hitl_route_tier_boundaries():
    mgr = HITLManager()

    # severity='info', confidence=0.90 -> 'auto'
    assert mgr.route(severity="info", confidence=0.90) == "auto", "info+0.90 should be auto"
    print("  PASS: info+0.90 -> auto")

    # severity='info', confidence=0.50 -> 'review' (falls through to return 'review')
    assert mgr.route(severity="info", confidence=0.50) == "review", "info+0.50 should be review"
    print("  PASS: info+0.50 -> review")

    # severity='warning', confidence=0.75 -> 'review'
    assert mgr.route(severity="warning", confidence=0.75) == "review", "warning+0.75 should be review"
    print("  PASS: warning+0.75 -> review")

    # severity='critical', confidence=0.40 -> 'approve'
    assert mgr.route(severity="critical", confidence=0.40) == "approve", "critical+0.40 should be approve"
    print("  PASS: critical+0.40 -> approve")

    # severity='critical', confidence=0.80 -> 'review'
    assert mgr.route(severity="critical", confidence=0.80) == "review", "critical+0.80 should be review"
    print("  PASS: critical+0.80 -> review")

    # is_investor_update=True -> 'approve'
    assert mgr.route(severity="info", confidence=0.90, is_investor_update=True) == "approve", "investor update should be approve"
    print("  PASS: is_investor_update=True -> approve")


def test_02_hitl_route_extended():
    mgr = HITLManager()

    # blocking=True -> 'blocked'
    assert mgr.route_extended(severity="info", confidence=0.90, blocking=True) == "blocked", "blocking should be blocked"
    print("  PASS: blocking=True -> blocked")

    # approval_required=True -> 'approve'
    assert mgr.route_extended(severity="info", confidence=0.90, approval_required=True) == "approve", "approval_required should be approve"
    print("  PASS: approval_required=True -> approve")

    # risk_tolerance='conservative' -> lowers confidence by 0.1
    # info+0.90 -> adjusted to 0.80 -> 0.60<=0.80<0.85 -> review
    result = mgr.route_extended(severity="info", confidence=0.90, risk_tolerance="conservative")
    assert result == "review", f"conservative should lower confidence; got {result}"
    print("  PASS: risk_tolerance=conservative -> review (confidence lowered 0.1)")

    # risk_tolerance='aggressive' -> raises confidence by 0.1
    # info+0.80 -> adjusted to 0.90 -> >0.85 -> auto
    result = mgr.route_extended(severity="info", confidence=0.80, risk_tolerance="aggressive")
    assert result == "auto", f"aggressive should raise confidence; got {result}"
    print("  PASS: risk_tolerance=aggressive -> auto (confidence raised 0.1)")


def test_03_score_confidence():
    # Full formula check
    # 0.5 + 0.15(seen) + 0.8*0.15(quality) - 0.1*0.1(volatility) + (0.9-0.5)*0.2(accuracy)
    # = 0.5 + 0.15 + 0.12 - 0.01 + 0.08 = 0.84
    sc = score_confidence(
        pattern_seen_before=True,
        data_quality=0.8,
        metric_volatility=0.1,
        historical_accuracy=0.9,
    )
    assert abs(sc - 0.84) < 0.001, f"expected 0.84, got {sc}"
    print("  PASS: full formula -> 0.84")

    # No pattern seen, no data, no volatility -> base=0.5
    sc = score_confidence(
        pattern_seen_before=False,
        data_quality=0.0,
        metric_volatility=0.0,
    )
    assert abs(sc - 0.5) < 0.001, f"expected 0.5, got {sc}"
    print("  PASS: bare minimum -> 0.5")


def test_04_auto_tools():
    """checkin and flag are auto."""
    assert checkin_tool["hitl_tier"] == "auto", "checkin_tool should be auto"
    print("  PASS: schedule_customer_checkin is auto")

    assert flag_tool["hitl_tier"] == "auto", "flag_tool should be auto"
    print("  PASS: flag_churn_risk is auto")


def test_05_approve_tools():
    """draft_investor_update is approve."""
    assert draft_tool["hitl_tier"] == "approve", "draft_tool should be approve"
    print("  PASS: draft_investor_update is approve")


def test_06_review_tools():
    """pause_payment_retry is review."""
    assert pause_tool["hitl_tier"] == "review", "pause_tool should be review"
    print("  PASS: pause_payment_retry is review")


def test_07_tool_registry_query():
    """get_tools_for_tier and get_tools_for_pattern accuracy."""
    auto_tools = get_tools_for_tier("auto")
    assert len(auto_tools) == 2, f"expected 2 auto tools, got {len(auto_tools)}: {[t.name for t in auto_tools]}"
    print(f"  PASS: get_tools_for_tier('auto') -> {[t.name for t in auto_tools]}")

    review_tools = get_tools_for_tier("review")
    assert len(review_tools) == 1, f"expected 1 review tool, got {len(review_tools)}: {[t.name for t in review_tools]}"
    print(f"  PASS: get_tools_for_tier('review') -> {[t.name for t in review_tools]}")

    approve_tools = get_tools_for_tier("approve")
    assert len(approve_tools) == 1, f"expected 1 approve tool, got {len(approve_tools)}: {[t.name for t in approve_tools]}"
    print(f"  PASS: get_tools_for_tier('approve') -> {[t.name for t in approve_tools]}")

    # get_tools_for_pattern('FG-05') returns pause_failed_payment_retry
    fg05 = get_tools_for_pattern("FG-05")
    assert len(fg05) == 1, f"expected 1 tool for FG-05, got {len(fg05)}"
    assert fg05[0].name == "pause_failed_payment_retry", f"expected pause_failed_payment_retry, got {fg05[0].name}"
    print("  PASS: get_tools_for_pattern('FG-05') -> pause_failed_payment_retry")

    # get_tools_for_patterns(['FG-03', 'BG-04']) returns schedule_customer_checkin AND flag_churn_risk
    fg03_bg04 = get_tools_for_patterns(["FG-03", "BG-04"])
    names = {t.name for t in fg03_bg04}
    assert len(fg03_bg04) == 2, f"expected 2 tools for FG-03+BG-04, got {len(fg03_bg04)}: {names}"
    assert "schedule_customer_checkin" in names
    assert "flag_churn_risk_customer" in names
    print("  PASS: get_tools_for_patterns(['FG-03', 'BG-04']) -> schedule_customer_checkin + flag_churn_risk_customer")


def test_08_relevance_gate():
    # Finance keyword match
    r1 = evaluate_relevance("our burn rate is too high, runway only 30 days")
    assert "finance" in r1.triggered_domains, f"burn/runway should trigger finance; got {r1.triggered_domains}"
    print("  PASS: 'burn rate...runway' -> finance domain")

    # No match
    r2 = evaluate_relevance("how's the weather?")
    assert r2.should_respond is False, "weather should not respond"
    print("  PASS: 'how's the weather?' -> no response")

    # Ops keyword match
    r3 = evaluate_relevance("customers are churning, support tickets spiking")
    assert "ops" in r3.triggered_domains, f"support/tickets should trigger ops; got {r3.triggered_domains}"
    print("  PASS: 'support tickets spiking' -> ops domain")


def main():
    tests = [
        ("test_01: HITLManager.route() tier boundaries", test_01_hitl_route_tier_boundaries),
        ("test_02: HITLManager.route_extended() features", test_02_hitl_route_extended),
        ("test_03: score_confidence() formula", test_03_score_confidence),
        ("test_04: Tools — auto tier", test_04_auto_tools),
        ("test_05: Tools — approve tier", test_05_approve_tools),
        ("test_06: Tools — review tier", test_06_review_tools),
        ("test_07: Tool registry query accuracy", test_07_tool_registry_query),
        ("test_08: RelevanceGate accuracy", test_08_relevance_gate),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        print(f"\n{'='*60}")
        print(f"  {name}")
        print(f"{'='*60}")
        try:
            fn()
            passed += 1
            print(f"  \033[92mOK\033[0m")
        except Exception as e:
            print(f"  \033[91mFAIL: {e}\033[0m")
            failed += 1

    print(f"\n{'='*60}")
    print(f"  RESULTS: {passed} passed, {failed} failed")
    print(f"{'='*60}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
