"""
Relevance Gate — Pure code keyword router.

Per PRD Section 7: "Agent responds only if: keyword_hit OR (active_alert AND question)"
This is pure Python — zero LLM tokens. Fast and deterministic.

Key insight from PRD:
- Never responds to every message — that is noise
- Self-activates when domain keyword is triggered
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class RelevanceDecision:
    """Result of relevance gate evaluation."""

    should_respond: bool
    triggered_domains: list[str]
    reason: str


# Per PRD Section 7
DOMAIN_KEYWORDS = {
    "finance": [
        "burn", "runway", "revenue", "mrr", "budget", "cost",
        "raise", "invest", "plan", "price", "₹", "$", "spend",
        "churn", "arr", " ARR", "pricing", "payment",
    ],
    "ops": [
        "support", "ticket", "bug", "error", "churn", "usage",
        "feature", "feedback", "sentry", "user", "product",
        "deploy", "infrastructure", "aws", "cloud",
    ],
    "bi": [
        "metric", "dau", "mau", "retention", "cohort", "growth",
        "data", "dashboard", "report", "trend", "last month",
        "analytics", "activation", "adoption",
    ],
}


def evaluate_relevance(
    message: str,
    active_alerts: list[str] | None = None,
    mission_context: dict | None = None,
) -> RelevanceDecision:
    """Evaluate if a message triggers any domain agents.

    Per PRD Section 7:
    - Agent responds only if: keyword_hit OR (active_alert AND question)
    - Never responds to every message — that is noise

    Args:
        message: The founder's message to evaluate
        active_alerts: List of currently active alert IDs
        mission_context: Current MissionState (for contextual triggers)

    Returns:
        RelevanceDecision with triggered domains and reasoning
    """
    message_lower = message.lower()
    triggered = []

    # Check keyword matches
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in message_lower:
                triggered.append(domain)
                break

    # Per PRD: if active alert AND question asked, trigger domain
    # Question detection: "what", "how", "why", "should", "?"
    has_question = any(q in message_lower for q in ["what", "how", "why", "should", "?"])

    if active_alerts and has_question:
        # Add related domains based on active alerts
        for alert_id in active_alerts:
            if alert_id.startswith("FG-"):
                if "finance" not in triggered:
                    triggered.append("finance")
            elif alert_id.startswith("BG-"):
                if "bi" not in triggered:
                    triggered.append("bi")
            elif alert_id.startswith("OG-"):
                if "ops" not in triggered:
                    triggered.append("ops")

    # Deduplicate while preserving order
    triggered = list(dict.fromkeys(triggered))

    if triggered:
        reason = f"Keywords matched: {', '.join(triggered)}"
        if active_alerts and has_question:
            reason += f" (plus {len(active_alerts)} active alerts)"
        return RelevanceDecision(
            should_respond=True,
            triggered_domains=triggered,
            reason=reason,
        )

    return RelevanceDecision(
        should_respond=False,
        triggered_domains=[],
        reason="No domain keywords matched",
    )


def get_triggered_agents(message: str, active_alerts: list[str] | None = None) -> list[str]:
    """Get list of agent names that should respond to this message.

    Maps domain → agent name per PRD Section 7:

    | Domain | Agent |
    |--------|-------|
    | finance | Finance Guardian |
    | bi | BI Analyst |
    | ops | Ops Watch |

    Args:
        message: The founder's message
        active_alerts: Currently active alerts

    Returns:
        List of agent names to trigger
    """
    decision = evaluate_relevance(message, active_alerts)

    domain_to_agent = {
        "finance": "Finance Guardian",
        "bi": "BI Analyst",
        "ops": "Ops Watch",
    }

    return [domain_to_agent[d] for d in decision.triggered_domains]