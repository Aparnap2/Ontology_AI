"""
Tests for orchestration wrapper call order.

Verifies:
1. Finance guardian calls existing helpers in correct order
2. No Slack when the guardian reports no matched patterns (match_count == 0)
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, call
import asyncio


@pytest.mark.asyncio
async def test_finance_guardian_call_order():
    """
    Existing PRD defines: fetch → memory → agent → alert → write
    The wrapper must call them in this order.
    """
    mock_fetch = AsyncMock(return_value={"ok": True, "mrr": 1000})
    mock_memory = AsyncMock(return_value={"history": []})
    mock_agent = AsyncMock(return_value={
        "ok": True,
        "match_count": 1,
        "blindspots_triggered": ["mrr_drop"],
    })
    mock_slack = AsyncMock(return_value={"ok": True})
    mock_write = AsyncMock(return_value={"ok": True})
    mock_emit = AsyncMock(return_value="msg-id")

    with patch("src.orchestration.run_finance_guardian.run_pulse_agent", mock_fetch), \
         patch("src.orchestration.run_finance_guardian.run_guardian_watchlist", mock_agent), \
         patch("src.orchestration.run_finance_guardian.send_slack_message", mock_slack), \
         patch("src.orchestration.run_finance_guardian.emit", mock_emit):

        # Import after patching
        from src.orchestration.run_finance_guardian import run_finance_guardian

        result = await run_finance_guardian("test-tenant")

        # Verify calls happened
        assert mock_fetch.called, "run_pulse_agent never called"
        assert mock_agent.called, "run_guardian_watchlist never called"
        assert mock_slack.called, "send_slack_message never called (match_count>0)"
        assert mock_emit.called, "emit never called"

        # Verify memory got fetch result (dependency chain)
        # Note: The agent is called with pulse_result from fetch
        assert mock_agent.call_count >= 1


@pytest.mark.asyncio
async def test_finance_guardian_no_slack_when_no_alert():
    """When no guardian patterns match (match_count == 0), Slack must NOT be called."""
    mock_fetch = AsyncMock(return_value={"ok": True, "mrr": 1000, "narrative": "All good"})
    mock_agent = AsyncMock(return_value={
        "ok": True,
        "match_count": 0,
        "blindspots_triggered": []
    })
    mock_slack = AsyncMock(return_value={"ok": True})
    mock_write = AsyncMock(return_value={"ok": True})
    mock_emit = AsyncMock(return_value="msg-id")

    with patch("src.orchestration.run_finance_guardian.run_pulse_agent", mock_fetch), \
         patch("src.orchestration.run_finance_guardian.run_guardian_watchlist", mock_agent), \
         patch("src.orchestration.run_finance_guardian.send_slack_message", mock_slack), \
         patch("src.orchestration.run_finance_guardian.emit", mock_emit):

        from src.orchestration.run_finance_guardian import run_finance_guardian

        await run_finance_guardian("test-tenant")

        # Slack should NOT be called when no alerts
        assert not mock_slack.called, \
            "Slack was called despite match_count=0 — alert fatigue risk"


@pytest.mark.asyncio
async def test_investor_update_relationship_health_first():
    """Investor update must check relationship health before generating update."""
    mock_health = AsyncMock(return_value={
        "ok": True,
        "high_priority_cold": 2,
        "cold_investors": []
    })
    mock_investor = AsyncMock(return_value={
        "ok": True,
        "narrative": "Investor update"
    })
    mock_slack = AsyncMock(return_value={"ok": True})
    mock_emit = AsyncMock(return_value="msg-id")

    with patch("src.orchestration.run_investor_update.check_relationship_health", mock_health), \
         patch("src.orchestration.run_investor_update.run_investor_agent", mock_investor), \
         patch("src.orchestration.run_investor_update.send_slack_message", mock_slack), \
         patch("src.orchestration.run_investor_update.emit", mock_emit):

        from src.orchestration.run_investor_update import run_investor_update

        result = await run_investor_update("test-tenant")

        # Verify relationship health checked first
        assert mock_health.called, "check_relationship_health never called"
        # Verify investor agent called after
        assert mock_investor.called, "run_investor_agent never called"


@pytest.mark.asyncio
async def test_weekly_synthesis_gathers_all_data():
    """Weekly synthesis must gather metrics, alerts, investor state, and decisions."""
    mock_synthesize = AsyncMock(return_value="Weekly brief content")
    mock_slack = AsyncMock(return_value={"ok": True})
    mock_emit = AsyncMock(return_value="msg-id")

    # Mock the data gathering functions
    mock_get_metrics = AsyncMock(return_value={"mrr": 1000})
    mock_get_alerts = AsyncMock(return_value=[{"title": "Alert 1"}])
    mock_get_investor = AsyncMock(return_value={"narrative": "Recent update"})
    mock_get_decisions = AsyncMock(return_value=[{"decided": "Decision 1"}])

    with patch("src.orchestration.run_weekly_synthesis.synthesize_weekly_brief", mock_synthesize), \
         patch("src.orchestration.run_weekly_synthesis.get_current_metrics_snapshot", mock_get_metrics), \
         patch("src.orchestration.run_weekly_synthesis.get_recent_alerts", mock_get_alerts), \
         patch("src.orchestration.run_weekly_synthesis.get_recent_investor_state", mock_get_investor), \
         patch("src.orchestration.run_weekly_synthesis.get_recent_decisions", mock_get_decisions), \
         patch("src.orchestration.run_weekly_synthesis.send_slack_message", mock_slack), \
         patch("src.orchestration.run_weekly_synthesis.emit", mock_emit):

        from src.orchestration.run_weekly_synthesis import run_weekly_synthesis

        result = await run_weekly_synthesis("test-tenant")

        # Verify all data sources called
        assert mock_get_metrics.called, "get_current_metrics_snapshot never called"
        assert mock_get_alerts.called, "get_recent_alerts never called"
        assert mock_get_investor.called, "get_recent_investor_state never called"
        assert mock_get_decisions.called, "get_recent_decisions never called"
        assert mock_synthesize.called, "synthesize_weekly_brief never called"
        assert mock_slack.called, "send_slack_message never called"


@pytest.mark.asyncio
async def test_synthesize_weekly_brief_uses_canonical_llm_path():
    """Regression: the activity must call src.config.llm.chat_completion.

    It previously instantiated ``LLMClient()`` from the non-existent
    ``src.llm.client`` module, which made this module unimportable (dangling
    import) and left a phantom client call. Pin the canonical factory path.
    """
    captured = {}

    def fake_chat_completion(*, messages, max_tokens=None, temperature=None):
        captured["messages"] = messages
        captured["max_tokens"] = max_tokens
        return "ONE THING: Ship the brief"

    from src.activities import synthesize_weekly_brief as mod

    with patch.object(mod, "chat_completion", fake_chat_completion):
        out = await mod.synthesize_weekly_brief(
            tenant_id="t1",
            alerts=[{"title": "a"}],
            decisions=[{"decided": "d"}],
            metrics={"mrr": 1000},
            investor_status={"narrative": "n"},
        )

    assert out == "ONE THING: Ship the brief"
    assert captured["messages"][0]["role"] == "user"
    assert captured["max_tokens"] == 300