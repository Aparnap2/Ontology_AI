"""Tests for Session Layer - TDD approach.

Write failing tests FIRST, then implement code to pass them.
Tests for MissionState, Relevance Gate, and Session Context.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime


class TestRelevanceGate:
    """Relevance gate tests - pure Python, no LLM.

    Per PRD Section 7: Agent responds only if keyword_hit OR (active_alert AND question).
    """

    def setup_method(self):
        """Reset module-level cache and trust state to avoid cross-test pollution."""
        from src.services.trust_battery import reset_profiles
        reset_profiles()
        import src.session.relevance_gate as rg
        rg._trust_battery = None

    def test_finance_keywords_trigger(self):
        """Finance keywords should trigger finance domain."""
        from src.session.relevance_gate import evaluate_relevance, DOMAIN_KEYWORDS

        for keyword in DOMAIN_KEYWORDS["finance"][:5]:
            result = evaluate_relevance(f"I am worried about {keyword}")
            assert result.should_respond
            assert "finance" in result.triggered_domains

    def test_ops_keywords_trigger(self):
        """Ops keywords should trigger ops domain."""
        from src.session.relevance_gate import evaluate_relevance, DOMAIN_KEYWORDS

        for keyword in DOMAIN_KEYWORDS["ops"][:5]:
            result = evaluate_relevance(f"Having issues with {keyword}")
            assert result.should_respond
            assert "ops" in result.triggered_domains

    def test_bi_keywords_trigger(self):
        """BI keywords should trigger bi domain."""
        from src.session.relevance_gate import evaluate_relevance, DOMAIN_KEYWORDS

        for keyword in DOMAIN_KEYWORDS["bi"][:5]:
            result = evaluate_relevance(f"Looking at {keyword} metrics")
            assert result.should_respond
            assert "bi" in result.triggered_domains

    def test_no_keywords_returns_empty(self):
        """No keywords should return should_respond=False."""
        from src.session.relevance_gate import evaluate_relevance

        result = evaluate_relevance("Hello, how are you?")
        assert result.should_respond is False
        assert result.triggered_domains == []

    def test_active_alerts_with_question_triggers(self):
        """Active alerts + question should trigger even without keywords."""
        from src.session.relevance_gate import evaluate_relevance

        result = evaluate_relevance(
            "What about the alert?",
            active_alerts=["FG-01", "OG-02"]
        )
        assert result.should_respond is True

    def test_get_triggered_agents_maps_domain_to_agent(self):
        """get_triggered_agents returns correct agent names."""
        from src.session.relevance_gate import get_triggered_agents

        agents = get_triggered_agents("My burn rate is too high")
        assert "Finance Guardian" in agents

        agents = get_triggered_agents("My DAU is dropping")
        assert "BI Analyst" in agents

        agents = get_triggered_agents("Getting errors in Sentry")
        assert "Ops Watch" in agents


class TestMissionState:
    """MissionState dataclass tests.

    Per PRD Section 11: Shared context object read/written by all agents.
    """

    def test_mission_state_creation(self):
        """MissionState can be created with tenant_id."""
        from src.session.mission_state import MissionState

        state = MissionState(tenant_id="test-001")
        assert state.tenant_id == "test-001"
        assert state.burn_alert is False
        assert state.active_alerts is None

    def test_mission_state_all_fields(self):
        """MissionState has all PRD fields."""
        from src.session.mission_state import MissionState

        state = MissionState(
            tenant_id="test-001",
            runway_days=6,
            burn_alert=True,
            burn_severity="critical",
            mrr_trend="declining",
            churn_rate=4.5,
            error_spike=True,
            active_alerts="FG-01,OG-02",
            founder_focus="fundraising",
        )

        assert state.runway_days == 6
        assert state.burn_alert is True
        assert state.burn_severity == "critical"
        assert state.mrr_trend == "declining"
        assert state.churn_rate == 4.5
        assert state.error_spike is True
        assert "FG-01" in state.active_alerts


class TestRouter:
    """Router tests - Co-founder message routing.

    Per PRD Section 7: Routes messages to Employee Agents.
    Per PRD Section 220-224: Option C authority.
    """

    def setup_method(self):
        """Reset module-level cache and trust state to avoid cross-test pollution."""
        from src.services.trust_battery import reset_profiles
        reset_profiles()
        import src.session.relevance_gate as rg
        rg._trust_battery = None

    @pytest.mark.asyncio
    async def test_route_finance_message(self):
        """Route finance keywords to finance domain."""
        from src.agents.cofounder.router import Router

        router = Router()
        decision = await router.route(
            "My burn rate is increasing too fast",
            tenant_id="test-001"
        )

        assert decision.destination in ["finance", "escalate"]
        assert decision.triggered_agents is not None

    @pytest.mark.asyncio
    async def test_route_ops_message(self):
        """Route ops keywords to ops domain."""
        from src.agents.cofounder.router import Router

        router = Router()
        decision = await router.route(
            "Getting support tickets about a bug",
            tenant_id="test-001"
        )

        assert decision.destination in ["ops", "escalate"]

    @pytest.mark.asyncio
    async def test_route_investor_always_escalates(self):
        """Investor keywords always escalate per PRD Option C."""
        from src.agents.cofounder.router import Router

        router = Router()
        decision = await router.route(
            "Need to prepare investor update",
            tenant_id="test-001"
        )

        assert decision.should_escalate is True

    @pytest.mark.asyncio
    async def test_route_no_match_returns_none(self):
        """No keyword match returns none destination."""
        from src.agents.cofounder.router import Router

        router = Router()
        decision = await router.route(
            "What is the weather today?",
            tenant_id="test-001"
        )

        assert decision.destination == "none"


class TestReflector:
    """ACE Reflector tests - founder response scoring.

    Per PRD Section 249-257: Generator → Reflector → Curator loop.
    """

    def test_response_scores_per_prd(self):
        """Response scores match PRD Section 252."""
        from src.agents.cofounder.reflector import RESPONSE_SCORES, ResponseType

        assert RESPONSE_SCORES[ResponseType.ACKNOWLEDGED] == 1.0
        assert RESPONSE_SCORES[ResponseType.ACTED_ON] == 1.5
        assert RESPONSE_SCORES[ResponseType.IGNORED] == -0.5
        assert RESPONSE_SCORES[ResponseType.DISPUTED] == -0.5
        assert RESPONSE_SCORES[ResponseType.DISMISSED] == -1.5

    def test_response_type_enum_values(self):
        """Response types match PRD."""
        from src.agents.cofounder.reflector import ResponseType

        assert ResponseType.ACKNOWLEDGED.value == "acknowledged"
        assert ResponseType.ACTED_ON.value == "acted_on"
        assert ResponseType.IGNORED.value == "ignored"
        assert ResponseType.DISPUTED.value == "disputed"
        assert ResponseType.DISMISSED.value == "dismissed"