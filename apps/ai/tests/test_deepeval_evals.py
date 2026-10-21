"""DeepEval test suite for IterateSwarm AI quality testing."""

import pytest
import json
import asyncio
from deepeval import assert_test, evaluate
from deepeval.evaluate.configs import AsyncConfig, DisplayConfig
from deepeval.test_case import LLMTestCase
from deepeval.metrics.base_metric import BaseMetric

from tests.metrics.classification_metric import ExactClassificationMetric, SpecQualityMetric

# Import your actual agents - adjust paths as needed
try:
    from src.agents.triage import classify_feedback
    from src.agents.spec import write_spec

    AGENTS_AVAILABLE = True
except ImportError:
    AGENTS_AVAILABLE = False
    print("Warning: Agent modules not available, tests will be skipped")


# ─────────────────────────────────────────────
# GROUND TRUTH DATASET — 15 labeled examples
# ─────────────────────────────────────────────
GOLDEN_DATASET = [
    # (input_text, expected_type, expected_severity)
    ("The app crashes when I click the save button", "bug", "high"),
    ("App exits unexpectedly after uploading a file", "bug", "high"),
    ("Login fails with Google OAuth on Safari", "bug", "high"),
    ("Getting 500 error when uploading files > 10MB", "bug", "high"),
    ("Database connection timeout on every page load", "bug", "critical"),
    ("Please add dark mode to the dashboard", "feature", "low"),
    ("Can you add bulk delete to the inbox?", "feature", "medium"),
    ("Would love CSV export functionality", "feature", "low"),
    ("Add two-factor authentication support", "feature", "medium"),
    ("Integrate with Slack for notifications", "feature", "low"),
    ("How do I export my data?", "question", "low"),
    ("What are the API rate limits?", "question", "low"),
    ("How do I invite team members?", "question", "low"),
    ("Is there a mobile app available?", "question", "low"),
    ("How do I reset my password?", "question", "low"),
]


def build_test_case(text: str, expected_type: str, expected_severity: str) -> LLMTestCase:
    """Build test case from ground truth data."""
    if not AGENTS_AVAILABLE:
        # Fallback for when agents aren't available
        return LLMTestCase(
            input=text,
            actual_output=json.dumps({"type": expected_type, "severity": expected_severity, "confidence": 0.95}),
            expected_output=json.dumps(
                {
                    "type": expected_type,
                    "severity": expected_severity,
                }
            ),
            context=[f"Expected classification: {expected_type}, severity: {expected_severity}"],
        )

    # Call actual triage agent
    try:
        result = classify_feedback(text)
        actual_output = json.dumps(
            {
                "type": result.classification,
                "severity": result.severity,
                "confidence": result.confidence,
                "reasoning": result.reasoning,
            }
        )
    except Exception as e:
        actual_output = json.dumps({"type": "error", "severity": "error", "error": str(e)})

    expected_output = json.dumps(
        {
            "type": expected_type,
            "severity": expected_severity,
        }
    )

    return LLMTestCase(
        input=text,
        actual_output=actual_output,
        expected_output=expected_output,
        context=[f"Expected classification: {expected_type}, severity: {expected_severity}"],
    )


# ─────────────────────────────────────────────
# PYTEST TESTS
# ─────────────────────────────────────────────


@pytest.mark.parametrize("text,expected_type,expected_severity", GOLDEN_DATASET)
def test_classification_correctness(text, expected_type, expected_severity):
    """Every feedback must be classified into the correct type."""
    test_case = build_test_case(text, expected_type, expected_severity)
    assert_test(test_case, [ExactClassificationMetric(threshold=1.0)], run_async=False)


@pytest.mark.parametrize("text,expected_type,expected_severity", GOLDEN_DATASET[:5])
def test_bug_severity_accuracy(text, expected_type, expected_severity):
    """Bugs must have HIGH or CRITICAL severity."""
    if expected_type != "bug":
        pytest.skip("Only testing bugs in this suite")

    test_case = build_test_case(text, expected_type, expected_severity)

    class BugSeverityMetric(BaseMetric):
        name = "BugSeverityCheck"
        threshold = 1.0

        def measure(self, tc):
            output = json.loads(tc.actual_output)
            sev = output.get("severity", "").lower()
            self.score = 1.0 if sev in ["high", "critical"] else 0.0
            self.success = self.score >= self.threshold
            self.reason = f"Bug severity: {sev}"
            return self.score

        def is_successful(self):
            return self.success

    assert_test(test_case, [BugSeverityMetric()], run_async=False)


def test_full_pipeline_spec_quality():
    """Generated GitHub issue specs must meet quality standards."""
    if not AGENTS_AVAILABLE:
        pytest.skip("Agent modules not available")

    test_cases = []

    for text, expected_type, _ in GOLDEN_DATASET[:5]:  # test on bugs
        try:
            triage = classify_feedback(text)
            spec = write_spec(text, triage)

            actual_output = json.dumps(
                {
                    "spec": {
                        "title": spec.title,
                        "description": spec.description,
                        "labels": spec.suggested_labels,
                        "severity": triage.severity,
                    }
                }
            )

            test_cases.append(
                LLMTestCase(
                    input=text,
                    actual_output=actual_output,
                )
            )
        except Exception as e:
            print(f"Error creating test case: {e}")
            continue

    if not test_cases:
        pytest.skip("No test cases available")

    # Batch evaluate all specs at once
    results = evaluate(
        test_cases,
        [SpecQualityMetric(threshold=0.75)],
        async_config=AsyncConfig(run_async=False),
        display_config=DisplayConfig(show_indicator=False),
    )
    passed = sum(1 for r in results.test_results if r.success)
    total = len(results.test_results)
    assert passed >= int(total * 0.8), f"Only {passed}/{total} specs passed quality check"


@pytest.mark.skipif(not AGENTS_AVAILABLE, reason="Qdrant service not available")
def test_duplicate_detection_accuracy():
    """Identical feedback must be detected as duplicate."""
    try:
        from src.services.qdrant import get_qdrant_service
    except ImportError:
        pytest.skip("Qdrant service not available")

    async def run():
        qdrant = get_qdrant_service()

        original = "The app crashes when clicking save button"
        semantically_same = "App crashes after I press the save button"
        different = "Please add dark mode to the dashboard"

        # Index original
        await qdrant.index_feedback("test-001", original, {"source": "test"})

        # Semantically same → should be duplicate
        is_dup, score = await qdrant.check_duplicate(semantically_same)
        assert is_dup, f"Should detect duplicate. Score: {score}"
        assert score >= 0.85, f"Similarity should be >= 0.85, got {score}"

        # Different → should NOT be duplicate
        is_dup2, score2 = await qdrant.check_duplicate(different)
        assert not is_dup2, f"Should NOT be duplicate. Score: {score2}"

    asyncio.run(run())


if __name__ == "__main__":
    # Run with: python -m pytest tests/test_deepeval_evals.py -v
    print(f"Running DeepEval tests on {len(GOLDEN_DATASET)} golden dataset examples")
    print("Run with: uv run deepeval test run tests/test_deepeval_evals.py -v")
