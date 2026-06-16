import os
import logging
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi import SlackRequestHandler
from fastapi import FastAPI, Request

log = logging.getLogger(__name__)

app = AsyncApp(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)

if os.environ.get("SLACK_API_URL"):
    app.client.base_url = os.environ["SLACK_API_URL"] + "/"

fastapi_app = FastAPI()
handler = SlackRequestHandler(app=app)


@fastapi_app.post("/slack/events")
async def slack_events(request: Request):
    return await handler.handle(request)


async def get_tenant_from_slack_team(team_id: str) -> str:
    """Get tenant_id from Slack team_id."""
    from src.db import db

    rows = await db.fetch(
        "SELECT id FROM tenants WHERE slack_team_id = %s LIMIT 1",
        (team_id,)
    )
    if rows:
        return rows[0]["id"]

    default_tenant = os.environ.get("ACTIVE_TENANTS", "").split(",")[0]
    if default_tenant:
        return default_tenant

    return f"tenant-{team_id}"


@app.command("/trackguard")
async def handle_trackguard_command(ack, body, client):
    await ack()

    subcommand = body.get("text", "").strip().lower()
    team_id = body.get("team_id", "")
    user_id = body.get("user_id", "")
    trigger_id = body.get("trigger_id", "")

    if not team_id:
        await client.chat_postMessage(
            channel=user_id,
            text="⚠️ Could not identify your workspace. Please try again."
        )
        return

    if subcommand == "decide":
        try:
            from src.integrations.slack_client import SlackClient
            slack_client = SlackClient()
            result = await slack_client.client.views_open(
                trigger_id=trigger_id,
                view=_build_decision_modal()
            )
            if result.get("ok"):
                log.info(f"Opened decision modal for team {team_id}")
            else:
                await client.chat_postMessage(
                    channel=user_id,
                    text=f"⚠️ Could not open modal: {result.get('error', 'Unknown error')}"
                )
        except Exception as e:
            log.error(f"Error opening decision modal: {e}")
            await client.chat_postMessage(
                channel=user_id,
                text=f"⚠️ Error: {str(e)}"
            )
    elif subcommand == "help" or subcommand == "":
        await client.chat_postMessage(
            channel=user_id,
            text=(
                "*TrackGuard Commands:*\n"
                "• `/trackguard decide` — Log a decision to institutional memory\n"
                "• `/trackguard help` — Show this help\n\n"
                "Or just mention me: `@TrackGuard what's our runway?`"
            )
        )
    else:
        await client.chat_postMessage(
            channel=user_id,
            text=f"Unknown command: `{subcommand}`. Try `/trackguard decide` or `/trackguard help`"
        )


@app.view("decision_modal")
async def handle_decision_modal_submit(ack, body, client):
    await ack()

    team_id = body.get("team", {}).get("id", "")
    user_id = body.get("user", {}).get("id", "")

    if not team_id:
        await client.chat_postMessage(
            channel=user_id,
            text="⚠️ Could not identify your workspace."
        )
        return

    tenant_id = await get_tenant_from_slack_team(team_id)

    try:
        from src.integrations.slack_client import SlackClient
        slack_client = SlackClient()

        payload = body.get("view", {}).get("state", {}).get("values", {})
        decision_data = {
            "decided": payload.get("decision_block", {}).get("decision_input", {}).get("value", ""),
            "alternatives": payload.get("alternatives_block", {}).get("alternatives_input", {}).get("value", ""),
            "reasoning": payload.get("reasoning_block", {}).get("reasoning_input", {}).get("value", ""),
        }

        result = await slack_client.handle_modal_submit({"view": body.get("view", {})}, tenant_id)

        if result.get("ok"):
            await client.chat_postMessage(
                channel=user_id,
                text=f"✅ *Logged:* {decision_data['decided']}\nI'll surface this when it becomes relevant."
            )
        else:
            await client.chat_postMessage(
                channel=user_id,
                text=f"⚠️ Failed to log: {result.get('error', 'Unknown error')}"
            )
    except Exception as e:
        log.error(f"Error handling modal submit: {e}")
        await client.chat_postMessage(
            channel=user_id,
            text=f"⚠️ Error: {str(e)}"
        )


@app.action("acknowledge")
async def handle_acknowledge(ack, body, client):
    """Handle acknowledge button - route to button handler."""
    await ack()
    try:
        from src.integrations.slack_buttons import route_slack_button
        payload = {
            "actions": body.get("actions", []),
            "user": body.get("user", {}),
        }
        result = route_slack_button(payload)
        if result.reply_text:
            await client.chat_postMessage(
                channel=body.get("channel", {}).get("id", ""),
                thread_ts=body.get("message", {}).get("ts", ""),
                text=result.reply_text
            )
    except Exception as e:
        log.error(f"Error handling acknowledge button: {e}")


@app.action("dispute")
async def handle_dispute(ack, body, client):
    """Handle dispute button - route to button handler."""
    await ack()
    try:
        from src.integrations.slack_buttons import route_slack_button
        payload = {
            "actions": body.get("actions", []),
            "user": body.get("user", {}),
        }
        result = route_slack_button(payload)
        if result.reply_text:
            await client.chat_postMessage(
                channel=body.get("channel", {}).get("id", ""),
                thread_ts=body.get("message", {}).get("ts", ""),
                text=result.reply_text
            )
    except Exception as e:
        log.error(f"Error handling dispute button: {e}")


@app.action("show_breakdown")
async def handle_show_breakdown(ack, body, client):
    """Handle show breakdown button."""
    await ack()
    try:
        from src.integrations.slack_buttons import route_slack_button
        payload = {
            "actions": body.get("actions", []),
            "user": body.get("user", {}),
        }
        result = route_slack_button(payload)
        if result.reply_text:
            await client.chat_postMessage(
                channel=body.get("channel", {}).get("id", ""),
                thread_ts=body.get("message", {}).get("ts", ""),
                text=result.reply_text
            )
    except Exception as e:
        log.error(f"Error handling show_breakdown button: {e}")


@app.action("log_decision")
async def handle_log_decision(ack, body, client):
    """Handle log decision button."""
    await ack()
    try:
        from src.integrations.slack_buttons import route_slack_button
        payload = {
            "actions": body.get("actions", []),
            "user": body.get("user", {}),
        }
        result = route_slack_button(payload)
        if result.reply_text:
            await client.chat_postMessage(
                channel=body.get("channel", {}).get("id", ""),
                thread_ts=body.get("message", {}).get("ts", ""),
                text=result.reply_text
            )
    except Exception as e:
        log.error(f"Error handling log_decision button: {e}")


@app.event("message")
async def handle_channel_message(event, say):
    """Handle #trackguard channel messages.

    Per PRD V3.0 Step 5:
    message received -> write_session_message -> relevance gate -> agent routing -> memory
    """
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return

    channel_id = event.get("channel", "")
    trackguard_channel = os.environ.get("TRACKGUARD_CHANNEL_ID", "")
    if trackguard_channel and channel_id != trackguard_channel:
        return

    text = event.get("text", "").strip()
    if not text:
        return

    team_id = event.get("team", "") or event.get("team_id", "")
    if not team_id:
        log.warning("No team_id in message event")
        return

    tenant_id = await get_tenant_from_slack_team(team_id)
    user = event.get("user", "unknown")

    try:
        from src.session.context import write_session_message
        from src.session.relevance_gate import evaluate_relevance

        await write_session_message(tenant_id, "founder", text)

        decision = evaluate_relevance(text, tenant_id=tenant_id)

        if decision.should_respond:
            from src.agents.cofounder.router import route_message
            from src.agents.cofounder.correlation import CorrelationAgent
            from src.session.mission_state import get_mission_state, update_mission_state
            from src.session.memory_integration import SessionMemoryWriter

            log.info(
                "Triggered agents for %s: %s",
                tenant_id, decision.triggered_domains,
            )

            routing = await route_message(text, tenant_id)

            mission = await get_mission_state(tenant_id)
            mission.founder_focus = text[:200]

            cofounder = CorrelationAgent()
            signals = cofounder.detect(mission)

            await update_mission_state(mission)

            writer = SessionMemoryWriter(tenant_id)
            writer.write_message_as_episode(
                content=text,
                event_type="intent_detected",
                metadata={
                    "user": user,
                    "channel": channel_id,
                    "destination": routing.destination,
                    "signals": [s.name for s in signals],
                },
            )

            log.info(
                "Message routed: tenant=%s destination=%s signals=%d",
                tenant_id, routing.destination, len(signals),
            )
        else:
            log.debug("No agents triggered for message: %s", text[:50])

    except Exception as e:
        log.error("Error processing #trackguard message: %s", e)


def _build_decision_modal():
    """Build the decision logging modal view."""
    return {
        "type": "modal",
        "callback_id": "decision_modal",
        "title": {
            "type": "plain_text",
            "text": "Log Decision"
        },
        "submit": {
            "type": "plain_text",
            "text": "Remember This"
        },
        "blocks": [
            {
                "type": "input",
                "block_id": "decision_block",
                "label": {
                    "type": "plain_text",
                    "text": "What did you decide?"
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "decision_input",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "e.g., Hire Sarah as CTO"
                    }
                }
            },
            {
                "type": "input",
                "block_id": "alternatives_block",
                "label": {
                    "type": "plain_text",
                    "text": "What were the alternatives?"
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "alternatives_input",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "e.g., Wait 3 months, Hire externally"
                    },
                    "multiline": True
                },
                "optional": True
            },
            {
                "type": "input",
                "block_id": "reasoning_block",
                "label": {
                    "type": "plain_text",
                    "text": "Why did you decide this?"
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "reasoning_input",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Key factors, risks considered, etc."
                    },
                    "multiline": True
                }
            }
        ]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "3000"))
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port)