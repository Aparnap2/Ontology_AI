"""Tests for Slack Block Kit button routing - TDD Red phase."""
import pytest


class TestSlackButtonRouting:
    """Verify button payloads route to correct agent signals."""

    def test_acknowledged_button_routes_to_reflector(self):
        """Acknowledged button should trigger +1.0 feedback signal."""
        from src.integrations.slack_buttons import route_slack_button
        
        payload = {
            "actions": [{"name": "acknowledge", "value": "alert_123"}],
            "user": {"id": "U123"},
        }
        result = route_slack_button(payload)
        assert result.success == True
        assert result.action == "acknowledge"
        assert result.signal_sent == 1.0

    def test_dispute_button_routes_to_reflector(self):
        """Dispute button should trigger -1.0 feedback signal."""
        from src.integrations.slack_buttons import route_slack_button
        
        payload = {
            "actions": [{"name": "dispute", "value": "alert_123"}],
            "user": {"id": "U123"},
        }
        result = route_slack_button(payload)
        assert result.success == True
        assert result.action == "dispute"
        assert result.signal_sent == -1.0

    def test_unknown_button_returns_error(self):
        """Unknown button type should return error gracefully."""
        from src.integrations.slack_buttons import route_slack_button
        
        payload = {
            "actions": [{"name": "unknown_action", "value": "alert_123"}],
            "user": {"id": "U123"},
        }
        result = route_slack_button(payload)
        assert result.success == False
        assert "Unknown action" in result.error

    def test_no_actions_returns_error(self):
        """Empty actions should return error."""
        from src.integrations.slack_buttons import route_slack_button
        
        payload = {
            "actions": [],
            "user": {"id": "U123"},
        }
        result = route_slack_button(payload)
        assert result.success == False
        assert "No actions" in result.error

    def test_show_breakdown_action(self):
        """Show breakdown button should return breakdown text."""
        from src.integrations.slack_buttons import route_slack_button
        
        payload = {
            "actions": [{"name": "show_breakdown", "value": "alert_456"}],
            "user": {"id": "U123"},
        }
        result = route_slack_button(payload)
        assert result.success == True
        assert result.action == "show_breakdown"
        assert "alert_456" in result.reply_text

    def test_log_decision_action(self):
        """Log decision button should return confirmation."""
        from src.integrations.slack_buttons import route_slack_button
        
        payload = {
            "actions": [{"name": "log_decision", "value": "decision_789"}],
            "user": {"id": "U123"},
        }
        result = route_slack_button(payload)
        assert result.success == True
        assert result.action == "log_decision"
        assert result.reply_text is not None
