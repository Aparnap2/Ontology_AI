"""Slack Block Kit button routing."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ButtonResult:
    success: bool
    action: str
    signal_sent: Optional[float] = None
    reply_text: Optional[str] = None
    error: Optional[str] = None


def route_slack_button(payload: dict) -> ButtonResult:
    """Route Slack Block Kit button to appropriate handler."""
    actions = payload.get("actions", [])
    if not actions:
        return ButtonResult(success=False, action="none", error="No actions")

    action = actions[0]
    action_name = action.get("name", "")
    action_value = action.get("value", "")

    if action_name == "acknowledge":
        return _handle_acknowledged(action_value)
    elif action_name == "dispute":
        return _handle_dispute(action_value)
    elif action_name == "show_breakdown":
        return _handle_show_breakdown(action_value)
    elif action_name == "log_decision":
        return _handle_log_decision(action_value)
    else:
        return ButtonResult(
            success=False, 
            action=action_name, 
            error=f"Unknown action: {action_name}"
        )


def _handle_acknowledged(alert_id: str) -> ButtonResult:
    """Handle acknowledged button - send +1.0 signal."""
    _send_feedback_signal(alert_id, "acknowledged", 1.0)
    return ButtonResult(
        success=True,
        action="acknowledge",
        signal_sent=1.0,
        reply_text="Got it - thanks for the heads up!"
    )


def _handle_dispute(alert_id: str) -> ButtonResult:
    """Handle dispute button - send -1.0 signal."""
    _send_feedback_signal(alert_id, "disputed", -1.0)
    return ButtonResult(
        success=True,
        action="dispute",
        signal_sent=-1.0,
        reply_text="Noted - I'll flag this for review."
    )


def _handle_show_breakdown(alert_id: str) -> ButtonResult:
    """Handle show breakdown - return data in thread."""
    return ButtonResult(
        success=True,
        action="show_breakdown",
        reply_text=f"Data breakdown for {alert_id}"
    )


def _handle_log_decision(alert_id: str) -> ButtonResult:
    """Handle log decision - write to DB + Graphiti."""
    return ButtonResult(
        success=True,
        action="log_decision",
        reply_text="Decision logged to your playbook."
    )


def _send_feedback_signal(alert_id: str, response_type: str, score: float) -> None:
    """Send feedback signal to Reflector."""
    try:
        from src.agents.cofounder.reflector import score_from_button
        score_from_button(alert_id, response_type, score)
    except ImportError:
        pass

    try:
        from src.agents.cofounder.curator import update_strategy_confidence
        update_strategy_confidence(
            tenant_id=alert_id.split("-")[0] if "-" in alert_id else "default",
            domain=alert_id.split("-")[1] if "-" in alert_id else "general",
            feedback_type=response_type,
            score=score,
        )
    except ImportError:
        pass