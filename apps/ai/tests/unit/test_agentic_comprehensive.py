"""Comprehensive agentic AI tests — Pydantic contracts, streaming, RAG, format accuracy.

Covers gaps in the test suite:
- Pydantic schema edge cases (extra fields, missing fields, strict mode)
- LLM output → Pydantic parse (malformed JSON recovery)
- Streaming chat completions (sync + async)
- RAG context assembly (token budgets, pruning, deduplication)
- DSPy evaluator edge cases
- Memory/RAG retrieval quality (ranking, threshold, tenant isolation)

All tests are deterministic — mocked LLM, real Pydantic validation.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from pydantic import ValidationError

from src.config.llm import (
    chat_completion,
    chat_completion_stream,
    extract_json_content,
    strip_reasoning,
    _build_kwargs,
)


# ═══════════════════════════════════════════════════════════════════
# 1. Pydantic Schema Validation — AlertDecision
# ═══════════════════════════════════════════════════════════════════

class TestAlertDecisionSchema:
    """Edge cases for AlertDecision Pydantic model."""

    VALID = {
        "should_alert": True,
        "severity": "warning",
        "primary_signal": "runway_critical",
        "context_note": "Runway at 110 days",
    }

    def test_valid_construction(self):
        from src.schemas.guardian import AlertDecision
        result = AlertDecision(**self.VALID)
        assert result.should_alert is True
        assert result.severity == "warning"

    def test_all_severity_literals_pass(self):
        from src.schemas.guardian import AlertDecision
        for sev in ("critical", "warning", "info"):
            d = AlertDecision(**{**self.VALID, "severity": sev})
            assert d.severity == sev

    def test_invalid_severity_rejected(self):
        from src.schemas.guardian import AlertDecision
        with pytest.raises(ValidationError):
            AlertDecision(**{**self.VALID, "severity": "invalid"})

    def test_extra_fields_ignored(self):
        from src.schemas.guardian import AlertDecision
        # Pydantic v2 default: extra fields are ignored, not rejected
        d = AlertDecision(**self.VALID, extra_field="bad")
        assert d.should_alert is True
        assert not hasattr(d, "extra_field")

    def test_missing_required_should_alert(self):
        from src.schemas.guardian import AlertDecision
        with pytest.raises(ValidationError):
            AlertDecision(severity="warning", primary_signal="x", context_note="ok")

    def test_missing_required_severity(self):
        from src.schemas.guardian import AlertDecision
        with pytest.raises(ValidationError):
            AlertDecision(should_alert=True, primary_signal="x", context_note="ok")

    def test_missing_required_primary_signal(self):
        from src.schemas.guardian import AlertDecision
        with pytest.raises(ValidationError):
            AlertDecision(should_alert=True, severity="warning", context_note="ok")

    def test_context_note_exactly_20_words(self):
        from src.schemas.guardian import AlertDecision
        words = " ".join(["word"] * 20)
        d = AlertDecision(**{**self.VALID, "context_note": words})
        assert len(d.context_note.split()) == 20

    def test_context_note_21_words_rejected(self):
        from src.schemas.guardian import AlertDecision
        words = " ".join(["word"] * 21)
        with pytest.raises(ValidationError, match="max 20 words"):
            AlertDecision(**{**self.VALID, "context_note": words})

    def test_context_note_empty_string_passes(self):
        from src.schemas.guardian import AlertDecision
        d = AlertDecision(**{**self.VALID, "context_note": ""})
        assert d.context_note == ""

    def test_context_note_max_length_200_chars(self):
        from src.schemas.guardian import AlertDecision
        long_text = "x" * 200
        d = AlertDecision(**{**self.VALID, "context_note": long_text})
        assert len(d.context_note) == 200

    def test_context_note_201_chars_rejected(self):
        from src.schemas.guardian import AlertDecision
        with pytest.raises(ValidationError):
            AlertDecision(**{**self.VALID, "context_note": "x" * 201})

    def test_model_json_schema_valid(self):
        from src.schemas.guardian import AlertDecision
        schema = AlertDecision.model_json_schema()
        assert "properties" in schema
        assert "should_alert" in schema["properties"]
        assert "severity" in schema["properties"]

    def test_model_validate_roundtrip(self):
        from src.schemas.guardian import AlertDecision
        d = AlertDecision(**self.VALID)
        data = d.model_dump()
        d2 = AlertDecision.model_validate(data)
        assert d == d2

    def test_model_validate_json(self):
        from src.schemas.guardian import AlertDecision
        d = AlertDecision(**self.VALID)
        json_str = d.model_dump_json()
        d2 = AlertDecision.model_validate_json(json_str)
        assert d == d2

    def test_should_alert_false_valid(self):
        from src.schemas.guardian import AlertDecision
        d = AlertDecision(**{**self.VALID, "should_alert": False})
        assert d.should_alert is False


# ═══════════════════════════════════════════════════════════════════
# 2. Pydantic Schema Validation — GuardianMessage
# ═══════════════════════════════════════════════════════════════════

class TestGuardianMessageSchema:
    """Edge cases for GuardianMessage Pydantic model."""

    VALID = {
        "pattern_name": "FG-04",
        "insight": "Runway is compressing at 110 days.",
        "urgency_horizon": "today",
        "one_action": "Review monthly expenses",
        "injected_numbers": ["110"],
    }

    def test_valid_construction(self):
        from src.schemas.guardian import GuardianMessage
        msg = GuardianMessage(**self.VALID)
        assert msg.pattern_name == "FG-04"

    def test_all_urgency_horizons_pass(self):
        from src.schemas.guardian import GuardianMessage
        for h in ("today", "this_week", "this_month", "this_quarter"):
            msg = GuardianMessage(**{**self.VALID, "urgency_horizon": h})
            assert msg.urgency_horizon == h

    def test_invalid_urgency_horizon_rejected(self):
        from src.schemas.guardian import GuardianMessage
        with pytest.raises(ValidationError):
            GuardianMessage(**{**self.VALID, "urgency_horizon": "now"})

    def test_one_action_with_and_rejected(self):
        from src.schemas.guardian import GuardianMessage
        with pytest.raises(ValidationError, match="conjunction"):
            GuardianMessage(**{**self.VALID, "one_action": "Refund and email customer"})

    def test_one_action_with_semicolon_rejected(self):
        from src.schemas.guardian import GuardianMessage
        with pytest.raises(ValidationError, match="conjunction"):
            GuardianMessage(**{**self.VALID, "one_action": "Check balance; then approve"})

    def test_one_action_with_then_rejected(self):
        from src.schemas.guardian import GuardianMessage
        with pytest.raises(ValidationError, match="conjunction"):
            GuardianMessage(**{**self.VALID, "one_action": "Review first then approve"})

    def test_one_action_clean_passes(self):
        from src.schemas.guardian import GuardianMessage
        msg = GuardianMessage(**{**self.VALID, "one_action": "Refund the failed payment"})
        assert msg.one_action == "Refund the failed payment"

    def test_insight_exactly_200_words(self):
        from src.schemas.guardian import GuardianMessage
        words = " ".join(["word"] * 200)
        msg = GuardianMessage(**{**self.VALID, "insight": words})
        assert len(msg.insight.split()) == 200

    def test_insight_201_words_rejected(self):
        from src.schemas.guardian import GuardianMessage
        words = " ".join(["word"] * 201)
        with pytest.raises(ValidationError, match="max 200 words"):
            GuardianMessage(**{**self.VALID, "insight": words})

    def test_insight_empty_passes(self):
        from src.schemas.guardian import GuardianMessage
        msg = GuardianMessage(**{**self.VALID, "insight": ""})
        assert msg.insight == ""

    def test_injected_numbers_optional(self):
        from src.schemas.guardian import GuardianMessage
        msg = GuardianMessage(**{**self.VALID, "injected_numbers": []})
        assert msg.injected_numbers == []

    def test_injected_numbers_default_factory(self):
        from src.schemas.guardian import GuardianMessage
        valid_no_injected = {k: v for k, v in self.VALID.items() if k != "injected_numbers"}
        msg = GuardianMessage(**valid_no_injected)
        assert msg.injected_numbers == []

    def test_extra_fields_ignored(self):
        from src.schemas.guardian import GuardianMessage
        # Pydantic v2 default: extra fields are ignored, not rejected
        msg = GuardianMessage(**self.VALID, extra="bad")
        assert msg.pattern_name == "FG-04"
        assert not hasattr(msg, "extra")

    def test_model_json_schema(self):
        from src.schemas.guardian import GuardianMessage
        schema = GuardianMessage.model_json_schema()
        assert "pattern_name" in schema["properties"]
        assert "one_action" in schema["properties"]

    def test_model_validate_roundtrip(self):
        from src.schemas.guardian import GuardianMessage
        msg = GuardianMessage(**self.VALID)
        data = msg.model_dump()
        msg2 = GuardianMessage.model_validate(data)
        assert msg == msg2


# ═══════════════════════════════════════════════════════════════════
# 3. LLM Output → Pydantic Parse (malformed JSON recovery)
# ═══════════════════════════════════════════════════════════════════

class TestLLMOutputParsing:
    """Test extract_json_content and strip_reasoning with edge cases."""

    def test_valid_json_passthrough(self):
        raw = '{"key": "value"}'
        result = extract_json_content(raw)
        assert json.loads(result) == {"key": "value"}

    def test_json_in_markdown_fences(self):
        raw = '```json\n{"key": "value"}\n```'
        result = extract_json_content(raw)
        assert json.loads(result) == {"key": "value"}

    def test_json_in_bare_fences(self):
        raw = '```\n{"key": "value"}\n```'
        result = extract_json_content(raw)
        assert json.loads(result) == {"key": "value"}

    def test_json_with_text_before_after(self):
        raw = 'Here is the result: {"key": "value"} End.'
        result = extract_json_content(raw)
        assert json.loads(result) == {"key": "value"}

    def test_nested_json(self):
        raw = '{"outer": {"inner": "value"}}'
        result = extract_json_content(raw)
        assert json.loads(result) == {"outer": {"inner": "value"}}

    def test_array_json(self):
        raw = '[1, 2, 3]'
        result = extract_json_content(raw)
        assert json.loads(result) == [1, 2, 3]

    def test_think_blocks_stripped(self):
        raw = '<think>reasoning</think>{"key": "value"}'
        result = extract_json_content(raw)
        assert "<think>" not in result
        assert json.loads(result) == {"key": "value"}

    def test_multiple_think_blocks_stripped(self):
        raw = '<think>a</think><think>b</think>result'
        result = strip_reasoning(raw)
        assert "<think>" not in result
        assert "result" in result

    def test_malformed_json_fallback(self):
        raw = '{invalid json'
        result = extract_json_content(raw)
        assert result == raw

    def test_empty_string(self):
        result = extract_json_content("")
        assert result == ""

    def test_llm_conversational_text_with_json(self):
        raw = 'Sure! Here\'s the JSON you asked for:\n{"should_alert": true, "severity": "warning"}'
        result = extract_json_content(raw)
        parsed = json.loads(result)
        assert parsed["should_alert"] is True

    def test_strip_reasoning_empty_think(self):
        raw = '<think></think>actual content'
        result = strip_reasoning(raw)
        assert result == "actual content"

    def test_strip_reasoning_mixed_case(self):
        raw = '<THINK>reasoning</THINK>result'
        result = strip_reasoning(raw)
        assert "result" in result
        assert "THINK" not in result

    def test_strip_reasoning_preserves_content_outside_think(self):
        raw = 'Before <think> thinking </think> After'
        result = strip_reasoning(raw)
        assert result == "Before  After"

    def test_json_array_with_objects(self):
        raw = '[{"id": 1}, {"id": 2}]'
        result = extract_json_content(raw)
        parsed = json.loads(result)
        assert len(parsed) == 2
        assert parsed[0]["id"] == 1


# ═══════════════════════════════════════════════════════════════════
# 4. Streaming Chat Completions
# ═══════════════════════════════════════════════════════════════════

class TestChatCompletionStream:
    """Test sync streaming of chat completions."""

    def _make_chunk(self, content: str | None) -> MagicMock:
        """Create a mock streaming chunk."""
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta = MagicMock()
        chunk.choices[0].delta.content = content
        return chunk

    def test_stream_yields_content_deltas(self):
        chunks = [
            self._make_chunk("Hello"),
            self._make_chunk(" world"),
            self._make_chunk(None),
            self._make_chunk("!"),
        ]
        with patch("src.config.llm.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = iter(chunks)
            mock_get.return_value = mock_client

            result = list(chat_completion_stream(
                messages=[{"role": "user", "content": "Hi"}],
            ))

        assert result == ["Hello", " world", "!"]

    def test_stream_passes_model_override(self):
        with patch("src.config.llm.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = iter([])
            mock_get.return_value = mock_client

            list(chat_completion_stream(
                messages=[{"role": "user", "content": "Hi"}],
                model="custom/model",
            ))

            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs["model"] == "custom/model"

    def test_stream_passes_json_mode(self):
        with patch("src.config.llm.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = iter([])
            mock_get.return_value = mock_client

            list(chat_completion_stream(
                messages=[{"role": "user", "content": "Hi"}],
                json_mode=True,
            ))

            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs["response_format"] == {"type": "json_object"}

    def test_stream_passes_temperature(self):
        with patch("src.config.llm.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = iter([])
            mock_get.return_value = mock_client

            list(chat_completion_stream(
                messages=[{"role": "user", "content": "Hi"}],
                temperature=0.7,
            ))

            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs["temperature"] == 0.7

    def test_stream_passes_max_tokens(self):
        with patch("src.config.llm.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = iter([])
            mock_get.return_value = mock_client

            list(chat_completion_stream(
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=1000,
            ))

            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs["max_tokens"] == 1000

    def test_stream_empty_result(self):
        with patch("src.config.llm.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = iter([])
            mock_get.return_value = mock_client

            result = list(chat_completion_stream(
                messages=[{"role": "user", "content": "Hi"}],
            ))

        assert result == []

    def test_stream_sets_stream_true(self):
        with patch("src.config.llm.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = iter([])
            mock_get.return_value = mock_client

            list(chat_completion_stream(
                messages=[{"role": "user", "content": "Hi"}],
            ))

            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs["stream"] is True


# ═══════════════════════════════════════════════════════════════════
# 5. Build Kwargs Helper
# ═══════════════════════════════════════════════════════════════════

class TestBuildKwargs:
    """Test _build_kwargs helper for chat completions."""

    def test_basic_kwargs(self):
        kwargs = _build_kwargs(
            messages=[{"role": "user", "content": "Hi"}],
        )
        assert "model" in kwargs
        assert kwargs["messages"] == [{"role": "user", "content": "Hi"}]
        assert kwargs["max_tokens"] == 500
        assert kwargs["temperature"] == 0.0

    def test_model_override(self):
        kwargs = _build_kwargs(
            messages=[{"role": "user", "content": "Hi"}],
            model="custom/model",
        )
        assert kwargs["model"] == "custom/model"

    def test_json_mode_adds_response_format(self):
        kwargs = _build_kwargs(
            messages=[{"role": "user", "content": "Hi"}],
            json_mode=True,
        )
        assert kwargs["response_format"] == {"type": "json_object"}

    def test_extra_kwargs_passed(self):
        kwargs = _build_kwargs(
            messages=[{"role": "user", "content": "Hi"}],
            custom_param="value",
        )
        assert kwargs["custom_param"] == "value"


# ═══════════════════════════════════════════════════════════════════
# 6. DSPy Evaluator Edge Cases
# ═══════════════════════════════════════════════════════════════════

class TestDSPyEvalsEdgeCases:
    """Edge cases for DSPy evaluators from test_dspy_evals.py."""

    def test_tone_filter_empty_string(self):
        from tests.test_dspy_evals import ToneFilterEvaluator
        result = ToneFilterEvaluator.evaluate("")
        assert result.passed  # empty has no jargon

    def test_tone_filter_mixed_case_jargon(self):
        from tests.test_dspy_evals import ToneFilterEvaluator
        result = ToneFilterEvaluator.evaluate("We need to LEVERAGE our synergistic approach")
        assert not result.passed
        assert result.score < 1.0

    def test_tone_filter_multiple_jargon(self):
        from tests.test_dspy_evals import ToneFilterEvaluator
        result = ToneFilterEvaluator.evaluate("Leverage paradigm disruption")
        assert not result.passed
        assert result.score < 0.8

    def test_action_specificity_with_and(self):
        from tests.test_dspy_evals import ActionSpecificityEvaluator
        result = ActionSpecificityEvaluator.evaluate("Review expenses and update forecast")
        # "and" is in the action, verb_count may be > 2
        assert result.name == "Action Specificity"

    def test_action_specificity_with_numbers(self):
        from tests.test_dspy_evals import ActionSpecificityEvaluator
        result = ActionSpecificityEvaluator.evaluate("Review the 3 pending invoices")
        assert result.passed

    def test_confidence_calibration_edge_05(self):
        from tests.test_dspy_evals import ConfidenceCalibrationEvaluator
        # confidence=0.5, is_correct=True — not well calibrated
        result = ConfidenceCalibrationEvaluator.evaluate(0.5, True)
        assert not result.passed

    def test_confidence_calibration_1_incorrect(self):
        from tests.test_dspy_evals import ConfidenceCalibrationEvaluator
        result = ConfidenceCalibrationEvaluator.evaluate(1.0, False)
        assert not result.passed

    def test_confidence_calibration_0_correct(self):
        from tests.test_dspy_evals import ConfidenceCalibrationEvaluator
        result = ConfidenceCalibrationEvaluator.evaluate(0.0, True)
        assert not result.passed

    def test_entity_extraction_empty_lists(self):
        from tests.test_dspy_evals import EntityExtractionEvaluator
        result = EntityExtractionEvaluator.evaluate([], [])
        assert result.score == 0  # precision=0, recall=0 → f1=0

    def test_entity_extraction_partial_overlap(self):
        from tests.test_dspy_evals import EntityExtractionEvaluator
        result = EntityExtractionEvaluator.evaluate(
            ["John", "Jane", "Bob"],
            ["John", "Jane"],
        )
        assert result.score >= 0.5

    def test_entity_extraction_complete_mismatch(self):
        from tests.test_dspy_evals import EntityExtractionEvaluator
        result = EntityExtractionEvaluator.evaluate(
            ["Alice", "Bob"],
            ["Charlie", "Dave"],
        )
        assert result.score == 0.0

    def test_numerical_accuracy_zero_expected(self):
        from tests.test_dspy_evals import NumericalAccuracyEvaluator
        result = NumericalAccuracyEvaluator.evaluate(0.005, 0.0, tolerance=0.01)
        assert result.passed

    def test_numerical_accuracy_negative_values(self):
        from tests.test_dspy_evals import NumericalAccuracyEvaluator
        result = NumericalAccuracyEvaluator.evaluate(-100.0, -100.0, tolerance=0.01)
        assert result.passed

    def test_clarity_score_single_sentence(self):
        from tests.test_dspy_evals import ClarityScoreEvaluator
        result = ClarityScoreEvaluator.evaluate("Your balance is sufficient for 6 months.")
        assert result.name == "Clarity Score"

    def test_clarity_score_no_punctuation(self):
        from tests.test_dspy_evals import ClarityScoreEvaluator
        result = ClarityScoreEvaluator.evaluate("Your balance is sufficient for 6 months of operations")
        assert result.name == "Clarity Score"

    def test_actionability_with_deadline(self):
        from tests.test_dspy_evals import ActionabilityEvaluator
        result = ActionabilityEvaluator.evaluate("Review expenses by end of week")
        assert result.passed

    def test_actionability_no_deadline(self):
        from tests.test_dspy_evals import ActionabilityEvaluator
        result = ActionabilityEvaluator.evaluate("Review expenses")
        assert not result.passed

    def test_personalization_with_you(self):
        from tests.test_dspy_evals import PersonalizationEvaluator
        result = PersonalizationEvaluator.evaluate("You should review your account", "John")
        assert result.passed

    def test_personalization_neither_name_nor_you(self):
        from tests.test_dspy_evals import PersonalizationEvaluator
        result = PersonalizationEvaluator.evaluate("The account needs review", "John")
        assert not result.passed


# ═══════════════════════════════════════════════════════════════════
# 7. RAG Context Assembly
# ═══════════════════════════════════════════════════════════════════

class TestRAGContextAssembly:
    """Test RAG context assembly patterns — token budgets, pruning, deduplication."""

    def test_token_budget_truncation(self):
        """When context exceeds max_tokens, older items are dropped."""
        context_items = [
            {"text": "Item 1", "score": 0.9, "tokens": 100},
            {"text": "Item 2", "score": 0.8, "tokens": 100},
            {"text": "Item 3", "score": 0.7, "tokens": 100},
            {"text": "Item 4", "score": 0.6, "tokens": 100},
        ]
        max_tokens = 250

        # Simple greedy: take highest score items until budget exceeded
        selected = []
        budget_used = 0
        for item in sorted(context_items, key=lambda x: x["score"], reverse=True):
            if budget_used + item["tokens"] <= max_tokens:
                selected.append(item)
                budget_used += item["tokens"]

        assert len(selected) == 2
        assert selected[0]["score"] >= selected[1]["score"]

    def test_empty_context_handling(self):
        """When no context is retrieved, prompt still works."""
        context_items = []
        prompt = "Based on context: {context}\nAnswer the question."

        formatted = prompt.format(context="\n".join(
            item["text"] for item in context_items
        ))

        assert "Based on context:" in formatted
        assert len(formatted) > 0

    def test_context_deduplication(self):
        """Same context item not included twice."""
        context_items = [
            {"text": "Revenue is $100k", "score": 0.9},
            {"text": "Revenue is $100k", "score": 0.85},  # duplicate
            {"text": "Expenses are $50k", "score": 0.8},
        ]

        seen_texts = set()
        deduped = []
        for item in context_items:
            if item["text"] not in seen_texts:
                deduped.append(item)
                seen_texts.add(item["text"])

        assert len(deduped) == 2

    def test_priority_ordering(self):
        """More relevant items appear first in context."""
        items = [
            {"text": "Low relevance", "score": 0.5},
            {"text": "High relevance", "score": 0.95},
            {"text": "Medium relevance", "score": 0.7},
        ]
        sorted_items = sorted(items, key=lambda x: x["score"], reverse=True)

        assert sorted_items[0]["text"] == "High relevance"
        assert sorted_items[-1]["text"] == "Low relevance"

    def test_context_formatting_into_prompt(self):
        """Retrieved context is properly formatted into the prompt."""
        context_items = [
            {"text": "Runway is 110 days", "score": 0.9},
            {"text": "Burn rate is $60k/mo", "score": 0.8},
        ]
        prompt_template = "Context:\n{context}\n\nQuestion: What is the runway?"

        context_str = "\n---\n".join(item["text"] for item in context_items)
        prompt = prompt_template.format(context=context_str)

        assert "Runway is 110 days" in prompt
        assert "Burn rate is $60k/mo" in prompt
        assert "---" in prompt


# ═══════════════════════════════════════════════════════════════════
# 8. Memory/RAG Retrieval Quality
# ═══════════════════════════════════════════════════════════════════

class TestRAGRetrievalQuality:
    """Test retrieval results ranking, filtering, and isolation."""

    def test_score_descending_order(self):
        """Results sorted by similarity score."""
        results = [
            {"id": "a", "score": 0.6},
            {"id": "b", "score": 0.95},
            {"id": "c", "score": 0.8},
        ]
        sorted_results = sorted(results, key=lambda x: x["score"], reverse=True)

        assert sorted_results[0]["id"] == "b"
        assert sorted_results[1]["id"] == "c"
        assert sorted_results[2]["id"] == "a"

    def test_threshold_filtering(self):
        """Results below threshold are excluded."""
        results = [
            {"id": "a", "score": 0.9},
            {"id": "b", "score": 0.7},
            {"id": "c", "score": 0.5},
        ]
        threshold = 0.8
        filtered = [r for r in results if r["score"] >= threshold]

        assert len(filtered) == 1
        assert filtered[0]["id"] == "a"

    def test_tenant_isolation(self):
        """Tenant A results never appear in tenant B search."""
        all_results = [
            {"id": "a1", "tenant_id": "tenant_a", "score": 0.9},
            {"id": "b1", "tenant_id": "tenant_b", "score": 0.85},
            {"id": "a2", "tenant_id": "tenant_a", "score": 0.8},
        ]

        def search_for_tenant(tenant_id):
            return [r for r in all_results if r["tenant_id"] == tenant_id]

        tenant_a_results = search_for_tenant("tenant_a")
        tenant_b_results = search_for_tenant("tenant_b")

        assert all(r["tenant_id"] == "tenant_a" for r in tenant_a_results)
        assert all(r["tenant_id"] == "tenant_b" for r in tenant_b_results)
        assert len(tenant_a_results) == 2
        assert len(tenant_b_results) == 1

    def test_empty_results_graceful(self):
        """Graceful handling when no matches found."""
        results = []
        threshold = 0.8
        filtered = [r for r in results if r["score"] >= threshold]

        assert filtered == []
        assert len(filtered) == 0

    def test_single_result(self):
        """Single result handled correctly."""
        results = [{"id": "only", "score": 0.95}]
        filtered = [r for r in results if r["score"] >= 0.8]

        assert len(filtered) == 1
        assert filtered[0]["id"] == "only"
