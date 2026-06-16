"""
Capture Exact LLM Responses from Each Agent.

This script runs each agent test and captures the EXACT LLM output
including tool calls, decisions, headlines, and reasoning.

Usage:
    cd /home/aparna/Desktop/iterate_swarm/apps/ai
    uv run pytest tests/test_llm_responses.py -v -s

Environment:
    - OLLAMA_BASE_URL: http://localhost:11434/v1
    - OLLAMA_CHAT_MODEL: sam860/LFM2:2.6b
    - OLLAMA_EMBED_MODEL: nomic-embed-text:latest
    - QDRANT_HOST: localhost
    - QDRANT_PORT: 6333
"""
import os
import sys
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add src to path for imports (resolve relative to this file)
SCRIPT_DIR = Path(__file__).parent
SRC_DIR = SCRIPT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parent))

# Set Ollama config BEFORE any imports
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434/v1"
os.environ["OLLAMA_CHAT_MODEL"] = "sam860/LFM2:2.6b"
os.environ["OLLAMA_EMBED_MODEL"] = "nomic-embed-text:latest"
os.environ["QDRANT_HOST"] = "localhost"
os.environ["QDRANT_PORT"] = "6333"
os.environ["QDRANT_COLLECTION"] = "trackguard_memory"

TENANT = "test-tenant-llm-capture"


def capture_llm_response(
    agent_name: str, test_name: str, state: dict, event: dict, agent: Any
) -> dict:
    """
    Run agent and capture exact LLM response.

    Args:
        agent_name: Name of the agent being tested
        test_name: Name of the test case
        state: Input state dictionary
        event: Input event dictionary
        agent: Agent instance to run

    Returns:
        dict with:
        - agent_name
        - test_name
        - input_state
        - input_event
        - llm_headline (exact output)
        - llm_do_this (exact output)
        - fire_telegram (decision)
        - urgency (decision)
        - is_good_news (decision)
        - output_json (full output)
        - execution_time_ms
        - timestamp
    """
    start = time.time()

    result = agent.run(state, event)

    end = time.time()
    execution_time_ms = int((end - start) * 1000)

    return {
        "agent_name": agent_name,
        "test_name": test_name,
        "input_state": state,
        "input_event": event,
        "llm_headline": result.get("headline", ""),
        "llm_do_this": result.get("do_this", ""),
        "fire_telegram": result.get("fire_telegram", False),
        "urgency": result.get("urgency", "low"),
        "is_good_news": result.get("is_good_news", False),
        "output_json": result.get("output_json", {}),
        "execution_time_ms": execution_time_ms,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def run_revenue_tracker_tests() -> list[dict]:
    """Run Revenue Tracker tests and capture LLM responses."""
    from src.agents.revenue_tracker import RevenueTrackerAgent

    agent = RevenueTrackerAgent()
    responses = []

    print("\n" + "=" * 80)
    print("REVENUE TRACKER AGENT — LLM RESPONSES")
    print("=" * 80)

    # Test 1: MRR Milestone Detection
    print("\n[TEST 1] MRR Milestone Detection (Crossing ₹1L)")
    print("-" * 80)
    state = {"tenant_id": f"{TENANT}-revenue-1", "last_30d_mrr": 98000}
    event = {
        "event_type": "PAYMENT_SUCCESS",
        "amount": 3500,
        "customer_name": "Acme",
    }
    response = capture_llm_response("RevenueTracker", "mrr_milestone", state, event, agent)
    responses.append(response)

    print(f"INPUT: MRR ₹{state['last_30d_mrr']:,} + Payment ₹{event['amount']:,} from {event['customer_name']}")
    print(f"LLM HEADLINE: {response['llm_headline']}")
    print(f"LLM DO_THIS: {response['llm_do_this']}")
    print(f"DECISION: fire_telegram={response['fire_telegram']}, is_good_news={response['is_good_news']}")
    print(f"EXECUTION TIME: {response['execution_time_ms']}ms")

    # Test 2: Stale Deal Detection
    print("\n[TEST 2] Stale Deal Detection (>7 days no contact)")
    print("-" * 80)
    state = {
        "tenant_id": f"{TENANT}-revenue-2",
        "pipeline_deals": [
            {
                "name": "Acme Corp",
                "amount": 50000,
                "stage": "NEGOTIATION",
                "last_contact_at": "2026-03-01T00:00:00Z",  # 17 days ago
            }
        ],
    }
    event = {"event_type": "TIME_TICK_WEEKLY"}
    response = capture_llm_response("RevenueTracker", "stale_deal", state, event, agent)
    responses.append(response)

    print(f"INPUT: Deal '{state['pipeline_deals'][0]['name']}' idle for 17 days")
    print(f"LLM HEADLINE: {response['llm_headline']}")
    print(f"LLM DO_THIS: {response['llm_do_this']}")
    print(f"DECISION: fire_telegram={response['fire_telegram']}, urgency={response['urgency']}")
    print(f"EXECUTION TIME: {response['execution_time_ms']}ms")

    # Test 3: MRR Higher Milestone (₹5L)
    print("\n[TEST 3] MRR Milestone Detection (Crossing ₹5L)")
    print("-" * 80)
    state = {"tenant_id": f"{TENANT}-revenue-3", "last_30d_mrr": 495000}
    event = {
        "event_type": "PAYMENT_SUCCESS",
        "amount": 8000,
        "customer_name": "TechCorp",
    }
    response = capture_llm_response("RevenueTracker", "mrr_5l_milestone", state, event, agent)
    responses.append(response)

    print(f"INPUT: MRR ₹{state['last_30d_mrr']:,} + Payment ₹{event['amount']:,} from {event['customer_name']}")
    print(f"LLM HEADLINE: {response['llm_headline']}")
    print(f"LLM DO_THIS: {response['llm_do_this']}")
    print(f"DECISION: fire_telegram={response['fire_telegram']}, is_good_news={response['is_good_news']}")
    print(f"EXECUTION TIME: {response['execution_time_ms']}ms")

    return responses


def run_cs_agent_tests() -> list[dict]:
    """Run CS Agent tests and capture LLM responses."""
    from src.agents.cs_agent import CSAgent

    agent = CSAgent()
    responses = []

    print("\n" + "=" * 80)
    print("CS AGENT — LLM RESPONSES")
    print("=" * 80)

    # Test 1: Churn Risk Detection
    print("\n[TEST 1] Churn Risk Detection (>7 days no login)")
    print("-" * 80)
    state = {
        "tenant_id": f"{TENANT}-cs-1",
        "days_since_last_login": 8,
        "onboarding_stage": "WELCOME",
        "customer_name": "Arjun",
    }
    event = {"event_type": "TIME_TICK_D7"}
    response = capture_llm_response("CSAgent", "churn_risk", state, event, agent)
    responses.append(response)

    print(f"INPUT: {state['customer_name']} hasn't logged in for {state['days_since_last_login']} days")
    print(f"LLM HEADLINE: {response['llm_headline']}")
    print(f"LLM DO_THIS: {response['llm_do_this']}")
    print(f"DECISION: fire_telegram={response['fire_telegram']}, urgency={response['urgency']}")
    print(f"EXECUTION TIME: {response['execution_time_ms']}ms")

    # Test 2: New User Signup
    print("\n[TEST 2] New User Signup Welcome")
    print("-" * 80)
    state = {
        "tenant_id": f"{TENANT}-cs-2",
        "days_since_last_login": 0,
        "onboarding_stage": "WELCOME",
        "customer_name": "Priya",
    }
    event = {
        "event_type": "USER_SIGNED_UP",
        "customer_name": "Priya",
        "customer_id": "cust_123",
    }
    response = capture_llm_response("CSAgent", "new_signup", state, event, agent)
    responses.append(response)

    print(f"INPUT: New user {state['customer_name']} signed up")
    print(f"LLM HEADLINE: {response['llm_headline']}")
    print(f"LLM DO_THIS: {response['llm_do_this']}")
    print(f"DECISION: fire_telegram={response['fire_telegram']}, is_good_news={response['is_good_news']}")
    print(f"EXECUTION TIME: {response['execution_time_ms']}ms")

    # Test 3: Support Ticket Escalation
    print("\n[TEST 3] Support Ticket Escalation (3+ tickets in 48h)")
    print("-" * 80)
    state = {
        "tenant_id": f"{TENANT}-cs-3",
        "days_since_last_login": 1,
        "onboarding_stage": "DONE",
        "customer_name": "Rahul",
        "tickets_last_48h": 3,
    }
    event = {
        "event_type": "SUPPORT_TICKET_CREATED",
        "body": "I'm having trouble with the API integration. It's not working at all.",
    }
    response = capture_llm_response("CSAgent", "ticket_escalation", state, event, agent)
    responses.append(response)

    print(f"INPUT: {state['customer_name']} filed {state['tickets_last_48h']} tickets in 48h")
    print(f"LLM HEADLINE: {response['llm_headline']}")
    print(f"LLM DO_THIS: {response['llm_do_this']}")
    print(f"DECISION: fire_telegram={response['fire_telegram']}, urgency={response['urgency']}")
    print(f"EXECUTION TIME: {response['execution_time_ms']}ms")

    return responses


def run_chief_of_staff_tests() -> list[dict]:
    """Run Chief of Staff tests and capture LLM responses."""
    from src.agents.chief_of_staff import ChiefOfStaffAgent

    agent = ChiefOfStaffAgent()
    responses = []

    print("\n" + "=" * 80)
    print("CHIEF OF STAFF AGENT — LLM RESPONSES")
    print("=" * 80)

    # Test 1: Weekly Briefing Synthesis
    print("\n[TEST 1] Weekly Briefing (10 inputs → max 5 items)")
    print("-" * 80)
    state = {
        "tenant_id": f"{TENANT}-cos-1",
        "agent_outputs": [
            {"headline": "AWS spike detected", "urgency": "high", "is_good_news": False},
            {"headline": "Runway at 8 months", "urgency": "low", "is_good_news": False},
            {"headline": "Deal with Acme stalled", "urgency": "warn", "is_good_news": False},
            {"headline": "New hire Priya joins Monday", "urgency": "low", "is_good_news": True},
            {"headline": "GST due in 5 days", "urgency": "high", "is_good_news": False},
            {"headline": "MRR crossed ₹5L", "urgency": "low", "is_good_news": True},
            {"headline": "3 invoices overdue", "urgency": "warn", "is_good_news": False},
            {"headline": "Azure costs up 15%", "urgency": "low", "is_good_news": False},
            {"headline": "Customer churn risk: Arjun", "urgency": "high", "is_good_news": False},
            {"headline": "New feature launched", "urgency": "low", "is_good_news": True},
        ],
    }
    event = {"event_type": "TIME_TICK_WEEKLY"}
    response = capture_llm_response("ChiefOfStaff", "weekly_briefing", state, event, agent)
    responses.append(response)

    print(f"INPUT: 10 agent outputs (mixed urgency)")
    print(f"LLM HEADLINE: {response['llm_headline'][:200]}...")
    print(f"ITEM COUNT: {response['output_json'].get('item_count', 0)} items (max 5)")
    print(f"DECISION: fire_telegram={response['fire_telegram']}")
    print(f"EXECUTION TIME: {response['execution_time_ms']}ms")

    # Test 2: Investor Draft
    print("\n[TEST 2] Investor Update Draft")
    print("-" * 80)
    state = {
        "tenant_id": f"{TENANT}-cos-2",
        "monthly_revenue": 500000,
        "burn_rate": 180000,
        "runway_months": 14.2,
        "last_30d_mrr": 480000,
    }
    event = {"event_type": "TIME_TICK_MONTHLY"}
    response = capture_llm_response("ChiefOfStaff", "investor_draft", state, event, agent)
    responses.append(response)

    print(f"INPUT: Revenue ₹{state['monthly_revenue']:,}, Burn ₹{state['burn_rate']:,}, Runway {state['runway_months']} months")
    print(f"LLM DRAFT PREVIEW: {response['output_json'].get('draft', '')[:300]}...")
    print(f"DECISION: fire_telegram={response['fire_telegram']}")
    print(f"EXECUTION TIME: {response['execution_time_ms']}ms")

    # Test 3: Quiet Week Briefing
    print("\n[TEST 3] Quiet Week Briefing (No agent outputs)")
    print("-" * 80)
    state = {
        "tenant_id": f"{TENANT}-cos-3",
        "agent_outputs": [],
    }
    event = {"event_type": "TIME_TICK_WEEKLY"}
    response = capture_llm_response("ChiefOfStaff", "quiet_week", state, event, agent)
    responses.append(response)

    print(f"INPUT: No agent outputs this week")
    print(f"LLM HEADLINE: {response['llm_headline']}")
    print(f"ITEM COUNT: {response['output_json'].get('item_count', 0)} items")
    print(f"DECISION: fire_telegram={response['fire_telegram']}")
    print(f"EXECUTION TIME: {response['execution_time_ms']}ms")

    return responses


def save_responses_to_file(all_responses: list[dict]) -> Path:
    """Save all LLM responses to JSON file."""
    output_dir = Path(__file__).parent.parent.parent.parent / "docs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "LLM_RESPONSES_CAPTURE.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_responses, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 80}")
    print(f"ALL LLM RESPONSES SAVED TO: {output_file.absolute()}")
    print(f"{'=' * 80}")

    return output_file


def generate_summary_report(all_responses: list[dict]) -> Path:
    """Generate markdown summary report."""
    output_dir = Path(__file__).parent.parent.parent.parent / "docs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "LLM_RESPONSES_SUMMARY.md"

    # Calculate metrics
    total_tests = len(all_responses)
    avg_execution_time = sum(r["execution_time_ms"] for r in all_responses) / total_tests
    telegram_alerts = sum(1 for r in all_responses if r["fire_telegram"])
    good_news_items = sum(1 for r in all_responses if r["is_good_news"])

    # Group by agent
    by_agent: dict[str, list[dict]] = {}
    for r in all_responses:
        agent = r["agent_name"]
        if agent not in by_agent:
            by_agent[agent] = []
        by_agent[agent].append(r)

    # Generate report
    report_lines = [
        "# TrackGuard v1.0.0-alpha — Exact LLM Responses",
        "## Captured from Real Ollama Inference",
        "",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Model:** {os.environ.get('OLLAMA_CHAT_MODEL', 'unknown')}",
        f"**Base URL:** {os.environ.get('OLLAMA_BASE_URL', 'unknown')}",
        f"**Total Tests:** {total_tests}",
        f"**Average Execution Time:** {avg_execution_time:.0f}ms",
        "",
        "---",
        "",
    ]

    # Agent summaries
    agent_names = {
        "RevenueTracker": "Revenue Tracker Agent",
        "CSAgent": "Customer Success Agent",
        "ChiefOfStaff": "Chief of Staff Agent",
    }

    for agent_key, agent_name in agent_names.items():
        if agent_key not in by_agent:
            continue

        report_lines.append(f"## {agent_name}")
        report_lines.append("")

        for i, r in enumerate(by_agent[agent_key], 1):
            report_lines.append(f"### Test {i}: {r['test_name'].replace('_', ' ').title()}")
            report_lines.append("")

            # Input summary
            if "finance" in r["test_name"]:
                if "runway" in r["test_name"]:
                    report_lines.append(
                        f"**Input:** Runway {r['input_state'].get('runway_months', 'N/A')} months"
                    )
                elif "anomaly" in r["test_name"]:
                    event = r["input_event"]
                    baseline = r["input_state"].get("vendor_baselines", {}).get(
                        event.get("vendor", ""), {}
                    )
                    avg = baseline.get("avg", 0)
                    report_lines.append(
                        f"**Input:** {event.get('vendor', 'Vendor')} bill ₹{event.get('amount', 0):,} "
                        f"({event.get('amount', 0) / avg:.1f}× usual ₹{avg:,})"
                    )
                    if "memory" in r["test_name"]:
                        report_lines.append(
                            "**Memory Context:** 'AWS spike March 2026 — training run for ML model.'"
                        )
            elif "revenue" in r["test_name"]:
                if "mrr" in r["test_name"]:
                    report_lines.append(
                        f"**Input:** MRR ₹{r['input_state'].get('last_30d_mrr', 0):,} + "
                        f"Payment ₹{r['input_event'].get('amount', 0):,}"
                    )
                elif "stale" in r["test_name"]:
                    deals = r["input_state"].get("pipeline_deals", [])
                    if deals:
                        report_lines.append(
                            f"**Input:** Deal '{deals[0].get('name', 'Unknown')}' idle for >7 days"
                        )
            elif "cs" in r["test_name"]:
                if "churn" in r["test_name"]:
                    report_lines.append(
                        f"**Input:** {r['input_state'].get('customer_name', 'User')} hasn't logged in for "
                        f"{r['input_state'].get('days_since_last_login', 0)} days"
                    )
                elif "signup" in r["test_name"]:
                    report_lines.append(
                        f"**Input:** New user {r['input_event'].get('customer_name', 'User')} signed up"
                    )
                elif "ticket" in r["test_name"]:
                    report_lines.append(
                        f"**Input:** {r['input_state'].get('customer_name', 'User')} filed "
                        f"{r['input_state'].get('tickets_last_48h', 0)} tickets in 48h"
                    )
            elif "cos" in r["test_name"] or "chief" in r["test_name"]:
                if "briefing" in r["test_name"]:
                    count = len(r["input_state"].get("agent_outputs", []))
                    report_lines.append(f"**Input:** {count} agent outputs (mixed urgency)")
                elif "investor" in r["test_name"]:
                    report_lines.append(
                        f"**Input:** Revenue ₹{r['input_state'].get('monthly_revenue', 0):,}, "
                        f"Burn ₹{r['input_state'].get('burn_rate', 0):,}, "
                        f"Runway {r['input_state'].get('runway_months', 0)} months"
                    )
                elif "quiet" in r["test_name"]:
                    report_lines.append("**Input:** No agent outputs this week")

            report_lines.append("")
            report_lines.append(f"**LLM Headline:** \"{r['llm_headline']}\"")
            if r["llm_do_this"]:
                report_lines.append(f"**LLM Do This:** \"{r['llm_do_this']}\"")
            report_lines.append(f"**Decision:** fire_telegram={r['fire_telegram']}, urgency={r['urgency']}")
            if "is_good_news" in r:
                report_lines.append(f", is_good_news={r['is_good_news']}")
            report_lines.append("")
            report_lines.append(f"**Execution Time:** {r['execution_time_ms']}ms")
            report_lines.append("")
            report_lines.append("---")
            report_lines.append("")

    # Quality metrics table
    report_lines.append("## Quality Metrics")
    report_lines.append("")
    report_lines.append("| Metric | Target | Actual |")
    report_lines.append("|--------|--------|--------|")

    # Calculate headline brevity (≤25 words)
    headlines_brief = sum(
        1 for r in all_responses if len(r["llm_headline"].split()) <= 25
    )
    brevity_pct = (headlines_brief / total_tests * 100) if total_tests > 0 else 0

    # Calculate jargon-free (check against banned list)
    banned_jargon = [
        "leverage",
        "synergy",
        "optimize",
        "streamline",
        "empower",
        "facilitate",
        "utilize",
        "implement",
        "strategic",
        "tactical",
    ]
    jargon_free = sum(
        1
        for r in all_responses
        if not any(j in r["llm_headline"].lower() for j in banned_jargon)
    )
    jargon_free_pct = (jargon_free / total_tests * 100) if total_tests > 0 else 0

    report_lines.append(
        f"| Jargon-free headlines | 100% | {jargon_free_pct:.0f}% ({jargon_free}/{total_tests}) |"
    )
    report_lines.append(
        f"| Headline brevity (≤25w) | 100% | {brevity_pct:.0f}% ({headlines_brief}/{total_tests}) |"
    )
    report_lines.append(
        f"| Telegram alerts fired | - | {telegram_alerts} |"
    )
    report_lines.append(
        f"| Good news items | - | {good_news_items} |"
    )
    report_lines.append(
        f"| Avg execution time | <5000ms | {avg_execution_time:.0f}ms |"
    )
    report_lines.append("")

    # Write file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"\n{'=' * 80}")
    print(f"SUMMARY REPORT SAVED TO: {output_file.absolute()}")
    print(f"{'=' * 80}")

    return output_file


def test_llm_responses() -> None:
    """Main test function that runs all agent tests."""
    print("=" * 80)
    print("TRACKGUARD v1.0.0-alpha — EXACT LLM RESPONSE CAPTURE")
    print("=" * 80)
    print(f"LLM: {os.environ['OLLAMA_CHAT_MODEL']} via {os.environ['OLLAMA_BASE_URL']}")
    print(f"Embeddings: {os.environ['OLLAMA_EMBED_MODEL']}")
    print(f"Memory: Qdrant at {os.environ['QDRANT_HOST']}:{os.environ['QDRANT_PORT']}")
    print(f"Timestamp: {datetime.now().isoformat()}")

    all_responses = []

    # Run all agent tests
    try:
        all_responses.extend(run_revenue_tracker_tests())
    except Exception as e:
        print(f"\n⚠️  Revenue Tracker tests failed: {e}")

    try:
        all_responses.extend(run_cs_agent_tests())
    except Exception as e:
        print(f"\n⚠️  CS Agent tests failed: {e}")

    try:
        all_responses.extend(run_chief_of_staff_tests())
    except Exception as e:
        print(f"\n⚠️  Chief of Staff tests failed: {e}")

    # Save to file
    if all_responses:
        save_responses_to_file(all_responses)
        generate_summary_report(all_responses)

        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total Tests Run: {len(all_responses)}")
        if all_responses:
            print(
                f"Average Execution Time: {sum(r['execution_time_ms'] for r in all_responses) / len(all_responses):.0f}ms"
            )
            print(f"Telegram Alerts Fired: {sum(1 for r in all_responses if r['fire_telegram'])}")
            print(f"Good News Items: {sum(1 for r in all_responses if r['is_good_news'])}")
        print("=" * 80)
    else:
        print("\n⚠️  No responses captured. Check that Ollama and Qdrant are running.")


if __name__ == "__main__":
    test_llm_responses()
