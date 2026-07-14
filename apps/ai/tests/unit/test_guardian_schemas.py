"""Tests for Guardian schemas - TDD approach.

These tests define the expected behavior BEFORE implementation.
Run FIRST - they should FAIL, then implement code to pass them.
"""
import pytest
from pydantic import ValidationError


_MOCK_LINEAGE = {
    "pattern_id": "test-pattern",
    "source_metrics": ["mrr"],
    "mission_context": ["test"],
    "raise_timeline_risk": "low",
    "suggested_tool_ids": [],
    "owner_agent": "test",
}


class TestGuardianMessage:
    """GuardianMessage schema tests."""

    def test_insight_max_200_words(self):
        """Insight must reject more than 200 words."""
        from src.schemas.guardian import GuardianMessage

        # 200 words should pass
        long_text = " ".join(["word"] * 200)
        msg = GuardianMessage(
            pattern_name="test_pattern",
            insight=long_text,
            urgency_horizon="today",
            one_action="Take action",
            injected_numbers=["100", "50"],
            lineage=_MOCK_LINEAGE,
        )
        assert len(msg.insight.split()) == 200

    def test_insight_rejects_over_200_words(self):
        """Insight with >200 words should raise ValidationError."""
        from src.schemas.guardian import GuardianMessage

        too_long = " ".join(["word"] * 201)
        with pytest.raises(ValidationError):
            GuardianMessage(
                pattern_name="test_pattern",
                insight=too_long,
                urgency_horizon="today",
                one_action="Take action",
                injected_numbers=["100"],
                lineage=_MOCK_LINEAGE,
            )

    def test_one_action_single_action(self):
        """one_action must be exactly ONE action - no conjunctions."""
        from src.schemas.guardian import GuardianMessage

        # Single action should pass
        msg = GuardianMessage(
            pattern_name="test",
            insight="Test insight",
            urgency_horizon="today",
            one_action="Do this",
            injected_numbers=[],
            lineage=_MOCK_LINEAGE,
        )
        assert "Do this" == msg.one_action

    def test_one_action_rejects_conjunctions(self):
        """one_action with 'and' or 'then' should raise."""
        from src.schemas.guardian import GuardianMessage

        with pytest.raises(ValidationError):
            GuardianMessage(
                pattern_name="test",
                insight="Test",
                urgency_horizon="today",
                one_action="Do this and then that",
                injected_numbers=[],
                lineage=_MOCK_LINEAGE,
            )

    def test_injected_numbers_optional(self):
        """injected_numbers can be empty list."""
        from src.schemas.guardian import GuardianMessage

        msg = GuardianMessage(
            pattern_name="test",
            insight="Test",
            urgency_horizon="today",
            one_action="Do it",
            injected_numbers=[],
            lineage=_MOCK_LINEAGE,
        )
        assert msg.injected_numbers == []


class TestAlertDecision:
    """AlertDecision schema tests."""
    
    def test_severity_valid_values(self):
        """Severity must be critical/warning/info."""
        from src.schemas.guardian import AlertDecision
        
        for severity in ["critical", "warning", "info"]:
            decision = AlertDecision(
                should_alert=True,
                severity=severity,
                primary_signal="test",
                context_note="Short context",
            )
            assert decision.severity == severity
    
    def test_severity_rejects_invalid(self):
        """Invalid severity should raise."""
        from src.schemas.guardian import AlertDecision
        
        with pytest.raises(ValidationError):
            AlertDecision(
                should_alert=True,
                severity="high",  # invalid
                primary_signal="test",
                context_note="Context",
            )
    
    def test_context_note_max_20_words(self):
        """context_note max 20 words."""
        from src.schemas.guardian import AlertDecision
        
        # 20 words should pass
        short = " ".join(["word"] * 20)
        decision = AlertDecision(
            should_alert=True,
            severity="warning",
            primary_signal="test",
            context_note=short,
        )
        assert len(short.split()) == 20
    
    def test_context_note_rejects_over_20(self):
        """context_note >20 words should raise."""
        from src.schemas.guardian import AlertDecision
        
        too_long = " ".join(["word"] * 21)
        with pytest.raises(ValidationError):
            AlertDecision(
                should_alert=True,
                severity="warning",
                primary_signal="test",
                context_note=too_long,
            )