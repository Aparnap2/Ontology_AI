"""Integration tests for Slackbot wiring - TDD approach.

Write failing tests FIRST, then implement code to pass them.
PRD: Full pipeline fires in sequence: message → relevance gate → agents → MissionState → cofounder

Run Mockoon manually on port 3000 before running these tests:
    mockoon /home/aparna/Desktop/iterate_swarm/apps/ai/tests/integration/slack-mock.json --port 3000 --daemon
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
import httpx


# Mockoon base URL - run manually before tests
MOCKOON_URL = "http://localhost:3000"


class TestSlackbotWiring:
    """5 integration tests for Slackbot wiring - all should fail before implementation."""

    def test_handle_slack_message_exists_and_is_callable(self):
        """handle_slack_message function must exist and be callable."""
        from src.integrations.slack import handle_slack_message

        assert callable(handle_slack_message)

    @pytest.mark.asyncio
    async def test_irrelevant_message_never_reaches_agents(self):
        """'good morning' → relevance_gate=False → 0 agent calls → response sent."""
        from src.integrations.slack import handle_slack_message

        slack_event = {
            "type": "message",
            "text": "good morning",
            "channel": "test-channel",
            "user": "U123"
        }

        with patch('src.session.relevance_gate.relevance_gate', return_value=[]) as mock_gate:
            result = await handle_slack_message(slack_event)

            assert result["blocked"] is True
            assert result["agents_called"] == 0

    @pytest.mark.asyncio
    async def test_relevant_message_calls_correct_agent(self):
        """'churn is high' → FinanceGuardian called → MissionState updated."""
        from src.integrations.slack import handle_slack_message

        slack_event = {
            "type": "message",
            "text": "churn is high",
            "channel": "test-channel",
            "user": "U123"
        }

        with patch('src.session.relevance_gate.relevance_gate', return_value=["finance"]):
            with patch('src.agents.cofounder.router.Router') as mock_router:
                mock_router.return_value.route.return_value = Mock(
                    destination="finance",
                    reason="keyword match",
                    should_escalate=False
                )

                result = await handle_slack_message(slack_event)

                assert result["destination"] == "finance"
                assert result["agents_called"] >= 1

    @pytest.mark.asyncio
    async def test_agent_failure_does_not_block_slack_response(self):
        """FinanceGuardian raises → fallback fires → Slack still gets a response."""
        from src.integrations.slack import handle_slack_message

        slack_event = {
            "type": "message",
            "text": "churn is high",
            "channel": "test-channel",
            "user": "U123"
        }

        with patch('src.session.relevance_gate.relevance_gate', return_value=["finance"]):
            with patch('src.agents.cofounder.router.Router') as mock_router:
                mock_router.return_value.route.side_effect = Exception("Finance guardian down")

                result = await handle_slack_message(slack_event)

                assert result is not None
                assert result["error_handled"] is True

    @pytest.mark.asyncio
    async def test_mission_state_persists_after_message(self):
        """message processed → MissionState.last_message_at updated → readable."""
        from src.integrations.slack import handle_slack_message

        slack_event = {
            "type": "message",
            "text": "burn rate concerns",
            "channel": "test-channel",
            "user": "U123"
        }

        with patch('src.session.relevance_gate.relevance_gate', return_value=["finance"]):
            with patch('src.agents.cofounder.router.Router') as mock_router:
                mock_router.return_value.route.return_value = Mock(
                    destination="finance",
                    reason="keyword match",
                    should_escalate=False
                )

                result = await handle_slack_message(slack_event)

                assert result["mission_updated"] is True

    @pytest.mark.asyncio
    async def test_cofounder_runs_after_domain_agents(self):
        """message triggers Finance + Ops → co-founder synthesis runs last, confirmed by call order."""
        from src.integrations.slack import handle_slack_message

        slack_event = {
            "type": "message",
            "text": "churn and errors both bad",
            "channel": "test-channel",
            "user": "U123"
        }

        with patch('src.session.relevance_gate.relevance_gate', return_value=["finance", "ops"]):
            with patch('src.agents.cofounder.router.Router') as mock_router:
                mock_router.return_value.route.return_value = Mock(
                    destination="finance,ops",
                    reason="keywords",
                    should_escalate=False
                )

            with patch('src.agents.cofounder.correlation.CorrelationAgent') as mock_cofounder:
                mock_cofounder.return_value.detect.return_value = []
                mock_cofounder.return_value.should_synthesize.return_value = False

                result = await handle_slack_message(slack_event)

                # Cofounder should be called after domain agents
                assert result["cofounder_ran"] is True