"""
Block Kit Formatter — Converts decision results to Slack Block Kit format.

Provides helpers for formatting guardian alerts, decision notifications,
and pending approval messages as Slack-ready blocks.
"""
from __future__ import annotations

from typing import Any, Optional

from .schemas import DecisionResultInput, PendingApproval


def format_decision_blocks(decision: DecisionResultInput) -> list[dict[str, Any]]:
    """
    Format decision result as Slack Block Kit blocks.

    Args:
        decision: Decision result to format

    Returns:
        List of Slack block kit blocks
    """
    blocks: list[dict[str, Any]] = []

    # Header with severity emoji
    severity_emoji = _get_severity_emoji(decision.severity)
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"{severity_emoji} {decision.pattern_name} Alert",
        }
    })

    # Main insight section
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*{decision.insight}*"
        }
    })

    # Metadata fields
    fields = [
        f"*Confidence:*\n{decision.confidence:.0%}",
        f"*Severity:*\n{decision.severity.upper()}",
        f"*Pattern:*\n{decision.pattern_name}",
        f"*Decision ID:*\n{decision.decision_id[:8]}...",
    ]

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "\n".join(fields)
        }
    })

    # HITL indicator if applicable
    if decision.hitl_required:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":warning: *Human Review Required* — This decision needs your approval."
            }
        })
        # Add action buttons for approve/reject
        blocks.append({
            "type": "actions",
            "block_id": f"hitl_{decision.decision_id}",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Approve"
                    },
                    "style": "primary",
                    "action_id": f"approve_{decision.decision_id}",
                    "value": decision.decision_id
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Reject"
                    },
                    "style": "danger",
                    "action_id": f"reject_{decision.decision_id}",
                    "value": decision.decision_id
                }
            ]
        })

    # Footer with timestamp
    blocks.append({
        "type": "context",
        "elements": [{
            "type": "plain_text",
            "text": f"TrackGuard Decision • {decision.occurred_at[:19].replace('T', ' ')}"
        }]
    })

    return blocks


def format_pending_approval_blocks(pending: PendingApproval) -> list[dict[str, Any]]:
    """
    Format pending approval item as Slack blocks.

    Args:
        pending: Pending approval to format

    Returns:
        List of Slack block kit blocks
    """
    blocks: list[dict[str, Any]] = []

    # Header
    severity_emoji = _get_severity_emoji(pending.severity)
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"{severity_emoji} Pending Approval: {pending.pattern_name}"
        }
    })

    # Insight
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*{pending.insight}*"
        }
    })

    # Created time
    blocks.append({
        "type": "context",
        "elements": [{
            "type": "plain_text",
            "text": f"Created: {pending.created_at[:19].replace('T', ' ')} • ID: {pending.item_id[:8]}..."
        }]
    })

    return blocks


def format_plain_text(decision: DecisionResultInput) -> str:
    """
    Convert decision to plain text fallback for Telegram/mocking.

    Args:
        decision: Decision to convert

    Returns:
        Plain text representation
    """
    severity_emoji = _get_severity_emoji(decision.severity)
    lines = [
        f"{severity_emoji} {decision.pattern_name} Alert",
        "",
        decision.insight,
        "",
        f"Confidence: {decision.confidence:.0%}",
        f"Severity: {decision.severity.upper()}",
    ]

    if decision.hitl_required:
        lines.extend([
            "",
            "⚠️ Human Review Required",
            f"Decision ID: {decision.decision_id}",
        ])

    return "\n".join(lines)


def _get_severity_emoji(severity: str) -> str:
    """Map severity to emoji."""
    return {
        "critical": "🔴",
        "warning": "🟡",
        "info": "🟢",
    }.get(severity.lower(), "⚪")


def format_slack_blocks(
    title: str,
    metrics: Optional[dict[str, Any]] = None,
    highlights: Optional[list[str]] = None,
    footer: Optional[str] = None
) -> list[dict[str, Any]]:
    """
    Generic Slack Block Kit helper for custom messages.

    Args:
        title: Main title/heading
        metrics: Optional dict of metric name -> value
        highlights: Optional list of bullet points
        footer: Optional footer text

    Returns:
        List of Slack block kit blocks
    """
    blocks: list[dict[str, Any]] = []

    # Title section
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": title,
        }
    })

    # Metrics section
    if metrics:
        metric_text = "\n".join([f"• *{k}*: {v}" for k, v in metrics.items()])
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": metric_text,
            }
        })

    # Highlights section
    if highlights:
        highlights_text = "\n".join([f"• {h}" for h in highlights])
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Highlights:*\n{highlights_text}",
            }
        })

    # Footer
    if footer:
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "plain_text",
                "text": footer,
            }]
        })

    return blocks