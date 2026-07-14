"""
DSPy Evaluation Suite — OntologyAI v4.2 Phase 7.

Comprehensive evals for internal ops agents:
1. ToneFilter fidelity (jargon-free)
2. Action specificity (single action, not list)
3. Desk routing accuracy
4. HITL classification accuracy
5. Response quality
6. Confidence calibration
7. Entity extraction
8. Temporal reasoning
9. Numerical accuracy
10. Compliance checking
11. Risk assessment
12. Prioritization
13. Clarity score
14. Actionability
15. Personalization

Run with: pytest apps/ai/tests/test_dspy_evals.py -v
"""

import pytest
from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class EvalResult:
    """Result of a single evaluation."""
    name: str
    passed: bool
    score: float
    reason: str


# =============================================================================
# Evaluation Metrics
# =============================================================================

class ToneFilterEvaluator:
    """Evaluates jargon-free communication."""
    
    JARGON_TERMS = [
        "leverage", "synergy", "paradigm", "disrupt", "innovate",
        "scalable", "robust", "seamless", "holistic", "mission-critical",
        "best-in-class", "world-class", "cutting-edge", "state-of-the-art",
    ]
    
    @classmethod
    def evaluate(cls, text: str) -> EvalResult:
        """Check if text is jargon-free."""
        text_lower = text.lower()
        found_jargon = [term for term in cls.JARGON_TERMS if term in text_lower]
        
        passed = len(found_jargon) == 0
        score = 1.0 if passed else max(0.0, 1.0 - (len(found_jargon) * 0.2))
        
        return EvalResult(
            name="ToneFilter Fidelity",
            passed=passed,
            score=score,
            reason=f"Found jargon: {found_jargon}" if found_jargon else "No jargon detected"
        )


class ActionSpecificityEvaluator:
    """Evaluates if action is single and specific."""
    
    @classmethod
    def evaluate(cls, action: str) -> EvalResult:
        """Check if action is single and specific."""
        # Count action verbs (simplified)
        action_verbs = ["review", "check", "update", "create", "send", "schedule", "approve"]
        verb_count = sum(1 for verb in action_verbs if verb in action.lower())
        
        # Check for list indicators
        is_list = any(indicator in action for indicator in ["\n-", "\n*", "\n1.", "\n•"])
        
        passed = verb_count <= 2 and not is_list
        score = 1.0 if passed else 0.5
        
        return EvalResult(
            name="Action Specificity",
            passed=passed,
            score=score,
            reason="Multiple actions or list detected" if not passed else "Single specific action"
        )


class DeskRoutingEvaluator:
    """Evaluates desk routing accuracy."""
    
    EXPECTED_ROUTING = {
        "bank_statement": "finance",
        "new_hire": "people",
        "contract_uploaded": "legal",
        "revenue_anomaly": "intelligence",
        "saas_subscription": "it",
        "meeting_transcript": "admin",
    }
    
    @classmethod
    def evaluate(cls, event_type: str, routed_desk: str) -> EvalResult:
        """Check if routing is correct."""
        expected = cls.EXPECTED_ROUTING.get(event_type)
        passed = expected == routed_desk
        
        return EvalResult(
            name="Desk Routing Accuracy",
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=f"Expected {expected}, got {routed_desk}" if not passed else "Correct routing"
        )


class HITLClassificationEvaluator:
    """Evaluates HITL classification accuracy."""
    
    HIGH_RISK_EVENTS = {"bank_statement", "contract_uploaded", "security_audit"}
    MEDIUM_RISK_EVENTS = {"payroll_due", "hiring_request", "revenue_anomaly"}
    
    @classmethod
    def evaluate(cls, event_type: str, hitl_level: str) -> EvalResult:
        """Check if HITL classification is appropriate."""
        expected_level = "LOW"
        
        if event_type in cls.HIGH_RISK_EVENTS:
            expected_level = "HIGH"
        elif event_type in cls.MEDIUM_RISK_EVENTS:
            expected_level = "MEDIUM"
        
        passed = expected_level == hitl_level
        score = 1.0 if passed else 0.5
        
        return EvalResult(
            name="HITL Classification Accuracy",
            passed=passed,
            score=score,
            reason=f"Expected {expected_level}, got {hitl_level}" if not passed else "Correct classification"
        )


class ResponseQualityEvaluator:
    """Evaluates overall response quality."""
    
    @classmethod
    def evaluate(cls, response: Dict[str, Any]) -> EvalResult:
        """Check response quality."""
        required_fields = ["finding_type", "content", "action"]
        has_all_fields = all(field in response for field in required_fields)
        
        content_length = len(response.get("content", ""))
        has_adequate_content = 50 <= content_length <= 500
        
        passed = has_all_fields and has_adequate_content
        score = 1.0 if passed else 0.5
        
        return EvalResult(
            name="Response Quality",
            passed=passed,
            score=score,
            reason="Missing fields or inadequate content" if not passed else "High quality response"
        )


class ConfidenceCalibrationEvaluator:
    """Evaluates confidence score calibration."""
    
    @classmethod
    def evaluate(cls, confidence: float, is_correct: bool) -> EvalResult:
        """Check if confidence matches correctness."""
        # High confidence should correlate with correctness
        well_calibrated = (confidence > 0.8 and is_correct) or (confidence < 0.5 and not is_correct)
        
        passed = well_calibrated
        score = 1.0 if passed else 0.5
        
        return EvalResult(
            name="Confidence Calibration",
            passed=passed,
            score=score,
            reason=f"Confidence {confidence} doesn't match correctness {is_correct}" if not passed else "Well calibrated"
        )


class EntityExtractionEvaluator:
    """Evaluates entity extraction accuracy."""
    
    @classmethod
    def evaluate(cls, extracted: List[str], expected: List[str]) -> EvalResult:
        """Check entity extraction."""
        extracted_set = set(e.lower() for e in extracted)
        expected_set = set(e.lower() for e in expected)
        
        precision = len(extracted_set & expected_set) / len(extracted_set) if extracted_set else 0
        recall = len(extracted_set & expected_set) / len(expected_set) if expected_set else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        passed = f1 >= 0.8
        score = f1
        
        return EvalResult(
            name="Entity Extraction",
            passed=passed,
            score=score,
            reason=f"F1 score: {f1:.2f}"
        )


class TemporalReasoningEvaluator:
    """Evaluates temporal reasoning."""
    
    @classmethod
    def evaluate(cls, dates: Dict[str, str]) -> EvalResult:
        """Check temporal reasoning."""
        # Check if dates are in correct order
        start_date = dates.get("start_date", "")
        end_date = dates.get("end_date", "")
        
        # Simplified check - in production use proper date parsing
        passed = start_date <= end_date if start_date and end_date else True
        score = 1.0 if passed else 0.0
        
        return EvalResult(
            name="Temporal Reasoning",
            passed=passed,
            score=score,
            reason="Invalid date range" if not passed else "Valid temporal reasoning"
        )


class NumericalAccuracyEvaluator:
    """Evaluates numerical accuracy."""
    
    @classmethod
    def evaluate(cls, calculated: float, expected: float, tolerance: float = 0.01) -> EvalResult:
        """Check numerical accuracy."""
        if expected == 0:
            passed = abs(calculated) < tolerance
        else:
            relative_error = abs(calculated - expected) / abs(expected)
            passed = relative_error <= tolerance
        
        score = 1.0 if passed else max(0.0, 1.0 - relative_error)
        
        return EvalResult(
            name="Numerical Accuracy",
            passed=passed,
            score=score,
            reason=f"Expected {expected}, got {calculated}" if not passed else "Accurate calculation"
        )


class ComplianceCheckingEvaluator:
    """Evaluates compliance checking."""
    
    REQUIRED_COMPLIANCE = {
        "contract_uploaded": ["expiry_date", "parties", "terms"],
        "new_hire": ["tax_forms", "nda", "handbook_ack"],
    }
    
    @classmethod
    def evaluate(cls, event_type: str, compliance_items: List[str]) -> EvalResult:
        """Check compliance."""
        required = cls.REQUIRED_COMPLIANCE.get(event_type, [])
        if not required:
            return EvalResult(
                name="Compliance Checking",
                passed=True,
                score=1.0,
                reason="No compliance requirements"
            )
        
        missing = [item for item in required if item not in compliance_items]
        passed = len(missing) == 0
        score = 1.0 - (len(missing) / len(required))
        
        return EvalResult(
            name="Compliance Checking",
            passed=passed,
            score=score,
            reason=f"Missing: {missing}" if missing else "All compliance items present"
        )


class RiskAssessmentEvaluator:
    """Evaluates risk assessment."""
    
    @classmethod
    def evaluate(cls, risk_level: str, risk_factors: List[str]) -> EvalResult:
        """Check risk assessment."""
        # High risk should have multiple factors
        if risk_level == "HIGH":
            passed = len(risk_factors) >= 3
        elif risk_level == "MEDIUM":
            passed = len(risk_factors) >= 2
        else:
            passed = len(risk_factors) <= 1
        
        score = 1.0 if passed else 0.5
        
        return EvalResult(
            name="Risk Assessment",
            passed=passed,
            score=score,
            reason=f"Risk level {risk_level} doesn't match {len(risk_factors)} factors" if not passed else "Appropriate risk assessment"
        )


class PrioritizationEvaluator:
    """Evaluates task prioritization."""
    
    @classmethod
    def evaluate(cls, tasks: List[Dict[str, Any]]) -> EvalResult:
        """Check task prioritization."""
        if not tasks:
            return EvalResult(
                name="Prioritization",
                passed=True,
                score=1.0,
                reason="No tasks to prioritize"
            )
        
        # Check if tasks are sorted by priority
        priorities = [task.get("priority", 0) for task in tasks]
        is_sorted = all(priorities[i] >= priorities[i+1] for i in range(len(priorities)-1))
        
        passed = is_sorted
        score = 1.0 if passed else 0.5
        
        return EvalResult(
            name="Prioritization",
            passed=passed,
            score=score,
            reason="Tasks not sorted by priority" if not passed else "Correctly prioritized"
        )


class ClarityScoreEvaluator:
    """Evaluates response clarity."""
    
    @classmethod
    def evaluate(cls, text: str) -> EvalResult:
        """Check clarity score."""
        # Simple metrics
        sentences = text.count(".") + text.count("!") + text.count("?")
        words = len(text.split())
        
        avg_sentence_length = words / sentences if sentences > 0 else words
        
        # Ideal: 15-20 words per sentence
        passed = 10 <= avg_sentence_length <= 25
        score = min(1.0, max(0.0, 1.0 - abs(avg_sentence_length - 17.5) / 20))
        
        return EvalResult(
            name="Clarity Score",
            passed=passed,
            score=score,
            reason=f"Avg sentence length: {avg_sentence_length:.1f}" if not passed else "Clear writing"
        )


class ActionabilityEvaluator:
    """Evaluates actionability of recommendations."""
    
    ACTIONABLE_VERBS = ["review", "check", "update", "create", "send", "schedule", "approve", "reject", "contact", "verify"]
    
    @classmethod
    def evaluate(cls, recommendation: str) -> EvalResult:
        """Check if recommendation is actionable."""
        has_action_verb = any(verb in recommendation.lower() for verb in cls.ACTIONABLE_VERBS)
        has_deadline = any(word in recommendation.lower() for word in ["today", "tomorrow", "week", "month", "by ", "before "])
        
        passed = has_action_verb and has_deadline
        score = 1.0 if passed else (0.7 if has_action_verb else 0.3)
        
        return EvalResult(
            name="Actionability",
            passed=passed,
            score=score,
            reason="Missing action verb or deadline" if not passed else "Actionable recommendation"
        )


class PersonalizationEvaluator:
    """Evaluates personalization."""
    
    @classmethod
    def evaluate(cls, response: str, founder_name: str) -> EvalResult:
        """Check personalization."""
        is_personalized = founder_name.lower() in response.lower() or "you" in response.lower()
        
        passed = is_personalized
        score = 1.0 if passed else 0.5
        
        return EvalResult(
            name="Personalization",
            passed=passed,
            score=score,
            reason="Not personalized" if not passed else "Personalized response"
        )


# =============================================================================
# Test Suite
# =============================================================================

class TestDSPyEvals:
    """DSPy evaluation test suite."""
    
    def test_tone_filter_no_jargon(self):
        """Test ToneFilter with jargon-free text."""
        result = ToneFilterEvaluator.evaluate("Your cash runway is 6 months.")
        assert result.passed
        assert result.score == 1.0
    
    def test_tone_filter_with_jargon(self):
        """Test ToneFilter with jargon."""
        result = ToneFilterEvaluator.evaluate("Leverage our synergistic paradigm.")
        assert not result.passed
        assert result.score < 1.0
    
    def test_action_specificity_single(self):
        """Test action specificity with single action."""
        result = ActionSpecificityEvaluator.evaluate("Review monthly expenses")
        assert result.passed
    
    def test_action_specificity_list(self):
        """Test action specificity with list."""
        result = ActionSpecificityEvaluator.evaluate("Review expenses\n- Check budget\n- Update forecast")
        assert not result.passed
    
    def test_desk_routing_finance(self):
        """Test desk routing for finance."""
        result = DeskRoutingEvaluator.evaluate("bank_statement", "finance")
        assert result.passed
    
    def test_desk_routing_people(self):
        """Test desk routing for people."""
        result = DeskRoutingEvaluator.evaluate("new_hire", "people")
        assert result.passed
    
    def test_hitl_classification_high(self):
        """Test HITL classification for high risk."""
        result = HITLClassificationEvaluator.evaluate("bank_statement", "HIGH")
        assert result.passed
    
    def test_hitl_classification_low(self):
        """Test HITL classification for low risk."""
        result = HITLClassificationEvaluator.evaluate("meeting_transcript", "LOW")
        assert result.passed
    
    def test_response_quality_complete(self):
        """Test response quality with complete response."""
        result = ResponseQualityEvaluator.evaluate({
            "finding_type": "cfo",
            "content": "Your cash runway is 6 months at current burn rate. Consider reducing expenses.",
            "action": "Review monthly expenses"
        })
        assert result.passed
    
    def test_confidence_calibration_correct(self):
        """Test confidence calibration when correct."""
        result = ConfidenceCalibrationEvaluator.evaluate(0.95, True)
        assert result.passed
    
    def test_entity_extraction_accurate(self):
        """Test entity extraction."""
        result = EntityExtractionEvaluator.evaluate(
            ["John Doe", "Software Engineer"],
            ["John Doe", "Software Engineer"]
        )
        assert result.score >= 0.8
    
    def test_numerical_accuracy(self):
        """Test numerical accuracy."""
        result = NumericalAccuracyEvaluator.evaluate(100.5, 100.0, tolerance=0.01)
        assert result.passed
    
    def test_clarity_score_good(self):
        """Test clarity score with good writing."""
        result = ClarityScoreEvaluator.evaluate("Your balance is ₹500,000. This amount covers approximately 6 months of operating expenses at the current burn rate.")
        assert result.passed
    
    def test_actionability_complete(self):
        """Test actionability with complete recommendation."""
        result = ActionabilityEvaluator.evaluate("Review expenses by end of week")
        assert result.passed
    
    def test_personalization_present(self):
        """Test personalization."""
        result = PersonalizationEvaluator.evaluate("Hello John, your balance is...", "John")
        assert result.passed


# =============================================================================
# Integration Test
# =============================================================================

@pytest.mark.skipif(True, reason="Requires full agent setup")
class TestDSPyEvalsIntegration:
    """Integration tests with real agents."""
    
    def test_full_eval_suite(self):
        """Run full evaluation suite on agent output."""
        # TODO: Implement with real agent calls
        pass
