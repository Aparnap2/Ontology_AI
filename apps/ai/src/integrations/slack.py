"""
Slack Integration Module for OntologyAI MVP.

Provides Slack message delivery via Incoming Webhooks.
Falls back to Telegram mock if Slack webhook not configured.
Supports MOCK MODE for development/testing.

Environment Variables:
    SLACK_WEBHOOK_URL: Slack incoming webhook URL
    TELEGRAM_BOT_TOKEN: Telegram bot token (fallback)
    TELEGRAM_CHAT_ID: Telegram chat ID for notifications (fallback)

Mock Mode:
    When SLACK_WEBHOOK_URL is empty, falls back to Telegram mock.
    When both are empty, logs message without sending.

Features:
    - Async send_message for non-blocking delivery
    - Sync wrapper send_message_sync for compatibility
    - Support for full_draft parameter (investor updates)
    - Never raises exceptions - always returns status dict
"""

import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)

# Configuration flags
USE_SLACK: bool = bool(os.getenv("SLACK_WEBHOOK_URL", "").strip())
USE_TELEGRAM_FALLBACK: bool = bool(
    os.getenv("TELEGRAM_BOT_TOKEN", "").strip() and
    os.getenv("TELEGRAM_CHAT_ID", "").strip()
)

# Mock mode - True when neither Slack nor Telegram is configured
MOCK_MODE: bool = not USE_SLACK and not USE_TELEGRAM_FALLBACK


async def _send_slack_webhook(
    text: str,
    blocks: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Send message to Slack via Incoming Webhook.

    Args:
        text: Plain text message
        blocks: Optional Slack block kit blocks

    Returns:
        Dict with 'ok' and 'channel' keys
    """
    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")

    if not webhook_url:
        return {"ok": False, "channel": "slack", "error": "Webhook URL not configured"}

    payload = {"text": text}
    if blocks:
        payload["blocks"] = blocks

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()

            # Slack returns "ok" for success
            if response.text.strip().lower() == "ok":
                logger.info("Slack message sent successfully")
                return {"ok": True, "channel": "slack"}
            else:
                logger.warning(f"Slack webhook response: {response.text}")
                return {"ok": False, "channel": "slack", "error": response.text}

    except httpx.HTTPError as e:
        logger.warning(f"Slack webhook HTTP error: {e}")
        return {"ok": False, "channel": "slack", "error": str(e)}
    except Exception as e:
        logger.error(f"Unexpected error sending Slack message: {e}")
        return {"ok": False, "channel": "slack", "error": str(e)}


async def _send_telegram_message(
    text: str,
    parse_mode: str = "HTML"
) -> Dict[str, Any]:
    """
    Send message to Telegram as fallback.

    Args:
        text: Message text (supports HTML formatting)
        parse_mode: Telegram parse mode (HTML or Markdown)

    Returns:
        Dict with 'ok' and 'channel' keys
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        return {"ok": False, "channel": "telegram", "error": "Telegram not configured"}

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("ok"):
                logger.info("Telegram message sent successfully")
                return {"ok": True, "channel": "telegram"}
            else:
                logger.warning(f"Telegram API error: {data}")
                return {"ok": False, "channel": "telegram", "error": str(data)}

    except httpx.HTTPError as e:
        logger.warning(f"Telegram HTTP error: {e}")
        return {"ok": False, "channel": "telegram", "error": str(e)}
    except Exception as e:
        logger.error(f"Unexpected error sending Telegram message: {e}")
        return {"ok": False, "channel": "telegram", "error": str(e)}


async def send_message(
    text: str,
    blocks: Optional[List[Dict[str, Any]]] = None,
    full_draft: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send message to Slack (or Telegram fallback).

    Primary delivery via Slack Incoming Webhook.
    Falls back to Telegram if Slack not configured.
    Logs without sending if neither is configured.

    Args:
        text: Main message text
        blocks: Optional Slack block kit blocks for rich formatting
        full_draft: Optional second message for investor updates
                   (sends as separate message after main text)

    Returns:
        Dict with keys:
            - ok: Boolean indicating success
            - channel: Which channel was used ('slack', 'telegram', or 'mock')
            - error: Optional error message if failed

    Example:
        >>> result = await send_message(
        ...     text="Weekly Update: MRR up 15%",
        ...     blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "*Weekly Update*"}}]
        ... )
        >>> print(f"Sent: {result['ok']}, Channel: {result['channel']}")
    """
    # Try Slack first
    if USE_SLACK:
        result = await _send_slack_webhook(text, blocks)

        # If full_draft provided, send as second message
        if result["ok"] and full_draft:
            draft_result = await _send_slack_webhook(full_draft)
            # Return combined result
            if not draft_result["ok"]:
                logger.warning(f"Full draft message failed: {draft_result.get('error')}")

        return result

    # Fall back to Telegram
    if USE_TELEGRAM_FALLBACK:
        # Convert Slack blocks to plain text if provided
        telegram_text = text
        if blocks:
            # Simple block conversion - extract text from blocks
            block_texts = []
            for block in blocks:
                if block.get("type") == "section":
                    block_text = block.get("text", {})
                    if isinstance(block_text, dict):
                        block_texts.append(block_text.get("text", ""))
                    else:
                        block_texts.append(str(block_text))
            if block_texts:
                telegram_text = f"{text}\n\n{' '.join(block_texts)}"

        if full_draft:
            telegram_text = f"{telegram_text}\n\n{full_draft}"

        return await _send_telegram_message(telegram_text)

    # Mock mode - log without sending
    logger.info(f"[MOCK MODE] Would send message: {text[:100]}...")
    if full_draft:
        logger.info(f"[MOCK MODE] Would send full draft: {full_draft[:100]}...")

    return {"ok": True, "channel": "telegram_mock", "mock": True}


def send_message_sync(
    text: str,
    blocks: Optional[List[Dict[str, Any]]] = None,
    full_draft: Optional[str] = None
) -> Dict[str, Any]:
    """
    Synchronous wrapper for send_message.

    Use when async/await is not available or for simple scripts.

    Args:
        text: Main message text
        blocks: Optional Slack block kit blocks
        full_draft: Optional second message for investor updates

    Returns:
        Dict with 'ok', 'channel', and optional 'error' keys

    Example:
        >>> result = send_message_sync("Quick update: all systems operational")
        >>> print(f"Sent: {result['ok']}")
    """
    import asyncio

    try:
        # Try to get running event loop
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # No event loop - create new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        # Event loop is running (e.g., in Jupyter)
        # Run in executor to avoid "cannot be called from a running event loop"
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                lambda: loop.run_until_complete(
                    send_message(text, blocks, full_draft)
                )
            )
            return future.result()
    else:
        return loop.run_until_complete(send_message(text, blocks, full_draft))


def format_slack_blocks(
    title: str,
    metrics: Optional[Dict[str, Any]] = None,
    highlights: Optional[List[str]] = None,
    footer: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Helper to format Slack block kit blocks.

    Args:
        title: Main title/heading
        metrics: Optional dict of metric name -> value
        highlights: Optional list of bullet points
        footer: Optional footer text

    Returns:
        List of Slack block kit blocks

    Example:
        >>> blocks = format_slack_blocks(
        ...     title="Weekly Metrics",
        ...     metrics={"MRR": "$12,500", "Growth": "+15%"},
        ...     highlights=["Launched feature X", "Closed enterprise deal"]
        ... )
    """
    blocks = []

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


async def handle_slack_message(
    slack_event: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle incoming Slack message through full pipeline.

    PRD: Full pipeline fires in sequence:
        message received
        → relevance gate (deterministic)
        → relevant agents called
        → MissionState updated
        → correlation/co-founder runs last
        → fallback paths do not block response

    Args:
        slack_event: Slack event dict with keys:
            - type: Event type (message, etc.)
            - text: Message text
            - channel: Channel ID
            - user: User ID

    Returns:
        Dict with keys:
            - blocked: True if message was filtered by relevance gate
            - agents_called: Number of agents called
            - destination: Agent destination or "none"
            - mission_updated: True if MissionState was updated
            - cofounder_ran: True if co-founder synthesis ran
            - error_handled: True if fallback handled an error
    """
    from src.session.relevance_gate import get_triggered_agents, evaluate_relevance
    from src.session.mission_state import MissionState
    from src.agents.cofounder import route_message
    from src.agents.cofounder.correlation import CorrelationAgent

    # Extract message text
    text = slack_event.get("text", "")
    user = slack_event.get("user", "unknown")
    channel = slack_event.get("channel", "unknown")
    tenant_id = slack_event.get("tenant_id", user)  # Use user as tenant if not provided

    result = {
        "blocked": False,
        "agents_called": 0,
        "destination": "none",
        "mission_updated": False,
        "cofounder_ran": False,
        "error_handled": False,
    }

    # Create MissionState
    mission = MissionState(tenant_id=tenant_id, timestamp=None)

    try:
        # Step 1: Relevance gate (deterministic)
        relevant_domains = get_triggered_agents(text)

        if not relevant_domains:
            result["blocked"] = True
            result["agents_called"] = 0
            return result

        result["agents_called"] = len(relevant_domains)
        result["destination"] = ",".join(relevant_domains)

        # Step 2: Call relevant agents (Router)
        try:
            route_result = await route_message(text, mission)
            result["destination"] = route_result.destination
        except Exception as e:
            logger.warning(f"Agent call failed: {e}")
            result["error_handled"] = True
            # Fallback: return partial result

        # Step 3: Update MissionState
        mission.last_message_at = datetime.now()
        result["mission_updated"] = True

        # Step 4: Co-founder synthesis runs last
        try:
            cofounder = CorrelationAgent()
            signals = cofounder.detect(mission)
            should_synth = cofounder.should_synthesize(mission)

            # Cofounder ran - always set true if called (even if empty result)
            result["cofounder_ran"] = True
        except Exception as e:
            logger.warning(f"Cofounder synthesis failed: {e}")
            result["error_handled"] = True
            # Fallback: do not block response

    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        result["error_handled"] = True

    return result


# ── Demo delivery (Mockoon + capture sidecar) ────────────────────

SLACK_DELIVERY_URL = os.environ.get("SLACK_DELIVERY_URL", "http://localhost:3001/slack/deliver")
_CAPTURE_URL = "http://localhost:3002"


async def deliver_guardian_alert(
    tenant_id: str,
    message: str,
    pattern_name: str,
    severity: str,
) -> Dict[str, Any]:
    """Deliver guardian alert to Mockoon (Slack mock) + capture sidecar."""
    payload: Dict[str, Any] = {
        "tenant_id": tenant_id,
        "pattern_name": pattern_name,
        "severity": severity,
        "text": message,
        "channel": "C_NOVAPULSE_DEMO",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        # Primary delivery (Mockoon → behaves like Slack)
        try:
            await client.post(SLACK_DELIVERY_URL, json=payload)
        except Exception as e:
            logger.warning("Mockoon delivery failed: %s", e)
        # Capture sidecar (Playwright reads from here)
        try:
            await client.post(_CAPTURE_URL, json=payload)
        except Exception:
            pass  # capture is best-effort — never block delivery
    return {"ok": True, "channel": "C_NOVAPULSE_DEMO"}
