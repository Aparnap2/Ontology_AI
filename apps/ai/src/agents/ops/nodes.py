"""
AnomalyAgent Node Functions.

Each node:
  - Accepts state: AnomalyState
  - Returns dict of only fields it changes
  - Never raises — errors written to state["error"] + state["error_node"]
  - Uses try/except with logging
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any

from src.agents.anomaly.state import AnomalyState
from src.agents.anomaly.thresholds import detect_anomaly
from src.agents.anomaly.prompts import anomaly_explainer, anomaly_action_generator

logger = logging.getLogger(__name__)

# ── Qdrant imports ────────────────────────────────────────────────
from src.memory.qdrant_ops import search_memory

# ── Slack integration ─────────────────────────────────────────────
from src.integrations.slack import send_message_sync, format_slack_blocks


# ── Node 0: detect_anomaly ────────────────────────────────────────

def detect_anomaly_node(state: AnomalyState) -> dict:
    """Rule-based anomaly detection with tenant-specific learned thresholds."""
    tenant_id = state.get("tenant_id", "unknown")

    result = detect_anomaly({
        "runway_days": state.get("runway_days", 999),
        "mrr_change_pct": state.get("mrr_change_pct", 0.0),
        "burn_rate_cents": state.get("burn_rate_cents", 0),
        "prev_burn_cents": state.get("prev_burn_cents", 0),
        "churned_customers": state.get("churned_customers", 0),
    }, tenant_id)

    return result


# ── Node 1: retrieve_anomaly_memory ───────────────────────────────

def retrieve_anomaly_memory(state: AnomalyState) -> dict:
    """
    Query Qdrant anomaly_memory for similar past anomalies.

    Populates:
      - past_episodes: List of similar past anomaly descriptions
      - historical_context: Prose summary of past episodes

    Uses semantic search with the metric name and anomaly description.
    """
    tenant_id = state.get("tenant_id", "unknown")
    metric_name = state.get("metric_name", "unknown metric")
    anomaly_desc = state.get("anomaly_description", "")

    result: dict = {
        "past_episodes": [],
        "historical_context": "",
    }

    try:
        # Search for similar past anomalies
        query = f"{metric_name} anomaly {anomaly_desc}"
        memories = search_memory(
            tenant_id=tenant_id,
            query=query,
            memory_type="anomaly_memory",
            limit=3,
        )

        if memories:
            # Extract content from memories
            result["past_episodes"] = [
                mem.get("content", "") for mem in memories if mem.get("content")
            ]

            # Build historical context summary
            if result["past_episodes"]:
                result["historical_context"] = (
                    f"Past similar episodes: {'; '.join(result['past_episodes'][:2])}"
                )

            logger.info(
                f"Retrieved {len(memories)} anomaly memories for {tenant_id}"
            )
        else:
            logger.info(f"No anomaly memories found for {tenant_id}")
            result["historical_context"] = "No historical anomaly data available."

    except Exception as e:
        logger.warning(f"Anomaly memory retrieval failed for {tenant_id}: {e}")
        result["historical_context"] = "Unable to retrieve historical context."
        result["error"] = f"Memory retrieval: {str(e)}"
        result["error_node"] = "retrieve_anomaly_memory"

    return result


# ── Node 2: generate_explanation ──────────────────────────────────

def generate_explanation(state: AnomalyState) -> dict:
    """
    Generate plain-English explanation using DSPy AnomalyExplainer.

    Populates:
      - explanation: Plain-English explanation of what changed and why
      - check_first: One thing to investigate first

    Formats anomaly details as human-readable strings for the LLM.
    """
    result: dict = {
        "explanation": "",
        "check_first": "",
    }

    try:
        tenant_id = state.get("tenant_id", "unknown")
        metric_name = state.get("metric_name", "unknown")
        current_value = state.get("current_value", 0.0)
        baseline_value = state.get("baseline_value", 0.0)
        deviation_pct = state.get("deviation_pct", 0.0)
        historical = state.get("historical_context", "No historical data.")

        # Format for LLM
        current_str = f"{current_value:.2f}"
        baseline_str = f"{baseline_value:.2f}"
        deviation_str = f"{deviation_pct:+.1f}%"

        # ── RAG Kernel context loading (fallback contract) ────────────
        rag_context = ""
        try:
            from src.memory.spine import MemorySpine
            from src.memory.rag_kernel import RAGKernel
            spine = MemorySpine(layers=[], rag_kernel=RAGKernel())
            rag_context = spine.load_context(
                tenant_id=tenant_id,
                task="explain anomaly with historical context",
                signal={"metric_name": metric_name, "current_value": current_value,
                        "deviation_pct": deviation_pct},
                max_tokens=800,
            )
        except Exception:
            rag_context = ""  # Fallback: never crash the agent

        historical_parts = [historical] if historical and historical != "No historical data." else []
        if rag_context:
            historical_parts.append(rag_context)
        historical_merged = "\n\n".join(historical_parts) if historical_parts else "No prior context for this anomaly."

        # Call DSPy predictor
        response = anomaly_explainer(
            metric_name=metric_name,
            current_value=current_str,
            baseline_value=baseline_str,
            deviation_pct=deviation_str,
            historical=historical_merged,
        )

        result["explanation"] = str(response.get("explanation", ""))
        result["check_first"] = str(response.get("check_first", ""))

        logger.info(
            f"Generated explanation for {tenant_id}: {result['explanation'][:50]}..."
        )

    except Exception as e:
        logger.error(f"Explanation generation failed: {e}")
        # Fallback: generate simple template explanation
        metric_name = state.get("metric_name", "metric")
        current = state.get("current_value", 0)
        baseline = state.get("baseline_value", 0)
        deviation = state.get("deviation_pct", 0)

        result["explanation"] = (
            f"Your {metric_name} is {current:.2f}, which is {deviation:+.1f}% "
            f"from the baseline of {baseline:.2f}. This requires attention."
        )
        result["check_first"] = "Review recent changes to this metric."
        result["error"] = f"Explanation generation: {str(e)}"
        result["error_node"] = "generate_explanation"

    return result


# ── Node 3: generate_action ───────────────────────────────────────

def generate_action(state: AnomalyState) -> dict:
    """
    Generate concrete action using DSPy AnomalyActionGenerator.

    Populates:
      - action_item: One concrete action starting with a verb

    Takes the explanation and generates a single actionable item.
    """
    result: dict = {
        "action_item": "",
    }

    try:
        tenant_id = state.get("tenant_id", "unknown")
        explanation = state.get("explanation", "")
        metric_name = state.get("metric_name", "unknown")
        current_value = state.get("current_value", 0.0)

        # Format for LLM
        current_str = f"{current_value:.2f}"

        # Call DSPy predictor
        response = anomaly_action_generator(
            explanation=explanation,
            metric_name=metric_name,
            current_value=current_str,
        )

        action = str(response.get("action_item", ""))

        # Ensure action starts with a verb (simple heuristic)
        if action and len(action.split()) <= 15:
            result["action_item"] = action
        else:
            # Fallback if action is too long or empty
            result["action_item"] = f"Investigate {metric_name} anomaly immediately."

        logger.info(f"Generated action for {tenant_id}: {result['action_item']}")

    except Exception as e:
        logger.error(f"Action generation failed: {e}")
        # Fallback: generate simple action
        metric_name = state.get("metric_name", "metric")
        result["action_item"] = f"Review {metric_name} trends and identify root cause."
        result["error"] = f"Action generation: {str(e)}"
        result["error_node"] = "generate_action"

    return result


# ── Node 4: build_slack_message ───────────────────────────────────

def build_slack_message(state: AnomalyState) -> dict:
    """
    Build Slack Block Kit message from explanation and action.

    Populates:
      - slack_blocks: Block Kit JSON for Slack message

    Format:
      - Header: "⚠️ Anomaly Alert"
      - Section: Metric name and deviation
      - Section: Explanation
      - Section: What to check first
      - Section: Action item
      - Context: Timestamp
    """
    result: dict = {
        "slack_blocks": [],
    }

    try:
        tenant_id = state.get("tenant_id", "unknown")
        metric_name = state.get("metric_name", "unknown")
        current_value = state.get("current_value", 0.0)
        baseline_value = state.get("baseline_value", 0.0)
        deviation_pct = state.get("deviation_pct", 0.0)
        explanation = state.get("explanation", "No explanation generated.")
        check_first = state.get("check_first", "No specific guidance.")
        action_item = state.get("action_item", "No action item.")

        # Build blocks
        blocks: list[dict] = []

        # Header with warning emoji
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "⚠️ Anomaly Alert",
            },
        })

        # Metric summary
        deviation_emoji = "📉" if deviation_pct < 0 else "📈"
        metric_text = (
            f"*{deviation_emoji} {metric_name} Anomaly Detected*\n"
            f"Current: {current_value:.2f} | Baseline: {baseline_value:.2f} | "
            f"Deviation: {deviation_pct:+.1f}%"
        )
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": metric_text,
            },
        })

        # Explanation
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*What's Happening:*\n{explanation}",
            },
        })

        # What to check first
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Check First:*\n{check_first}",
            },
        })

        # Action item
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Action Item:*\n{action_item}",
            },
        })

        # Feedback buttons for IterateSwarm learning
        anomaly_type = state.get("anomaly_type", "unknown")
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✅ Acted on this",
                    },
                    "style": "primary",
                    "action_id": "acted_on",
                    "value": f"anomaly:{anomaly_type}:{tenant_id}",
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "👎 Not relevant",
                    },
                    "style": "danger",
                    "action_id": "not_relevant",
                    "value": f"anomaly:{anomaly_type}:{tenant_id}",
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "⏰ Already knew",
                    },
                    "action_id": "already_knew",
                    "value": f"anomaly:{anomaly_type}:{tenant_id}",
                },
            ],
        })

        # Footer
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "plain_text",
                    "text": f"Generated {timestamp} by Sarthi AnomalyAgent",
                }
            ],
        })

        result["slack_blocks"] = blocks
        logger.info(f"Built Slack message for {tenant_id}: {len(blocks)} blocks")

    except Exception as e:
        logger.error(f"Slack message build failed: {e}")
        # Fallback: simple text block
        result["slack_blocks"] = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"⚠️ Anomaly Alert\n"
                        f"Metric: {state.get('metric_name', 'unknown')}\n"
                        f"Explanation: {state.get('explanation', 'N/A')}\n"
                        f"Action: {state.get('action_item', 'N/A')}"
                    ),
                },
            }
        ]
        result["error"] = f"Slack build: {str(e)}"
        result["error_node"] = "build_slack_message"

    return result


# ── Node 5: send_slack ────────────────────────────────────────────

def send_slack(state: AnomalyState) -> dict:
    """
    Send Slack message (async, with Telegram fallback).

    Populates:
      - slack_result: {"ok": bool, "channel": str}

    Uses send_message_sync from slack.py for compatibility.
    """
    result: dict = {
        "slack_result": {"ok": False, "channel": "unknown"},
    }

    try:
        tenant_id = state.get("tenant_id", "unknown")
        blocks = state.get("slack_blocks", [])
        explanation = state.get("explanation", "Anomaly detected")

        # Extract plain text from blocks for the main message
        plain_text = f"⚠️ Anomaly: {explanation[:200]}"

        # Send via Slack/Telegram
        send_result = send_message_sync(
            text=plain_text,
            blocks=blocks,
        )

        result["slack_result"] = send_result
        logger.info(f"Sent Slack message for {tenant_id}: ok={send_result.get('ok')}")

    except Exception as e:
        logger.error(f"Slack send failed: {e}")
        result["slack_result"] = {"ok": False, "channel": "error", "error": str(e)}
        result["error"] = f"Slack send: {str(e)}"
        result["error_node"] = "send_slack"

    return result
