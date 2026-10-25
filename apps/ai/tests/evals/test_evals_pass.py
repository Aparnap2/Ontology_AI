"""
Pytest Wrappers for LLM Evals.

Provides pytest-compatible test functions for CI integration.
Each test checks if the corresponding eval set meets its target pass rate.

Run with:
    cd apps/ai && uv run pytest tests/evals/test_evals_pass.py -v

Tests:
- test_anomaly_evals_pass: Anomaly explanations ≥80%
- test_sql_evals_pass: Text-to-SQL ≥85%
- test_narrative_evals_pass: BI narratives ≥75%
"""
import os
import sys
import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evals.run_evals import (
    run_anomaly_evals,
    run_sql_evals,
    run_narrative_evals,
)


class TestAnomalyEvals:
    """Test anomaly explanation evaluations."""

    def test_anomaly_evals_pass(self):
        """
        Test that anomaly explanation evals meet target pass rate.

        Target: ≥80% pass rate across 20 scenarios.

        Evaluates:
        - Vendor mention
        - Amount mention
        - Multiple/ratio mention
        - Action recommendation
        - Urgency appropriateness
        """
        result = run_anomaly_evals()

        assert result.target_met, (
            f"Anomaly evals failed: {result.pass_rate:.1%} pass rate "
            f"(target: {result.target_pass_rate:.1%}). "
            f"Passed: {result.passed_scenarios}/{result.total_scenarios}"
        )

    def test_anomaly_evals_average_score(self):
        """Test that anomaly evals have good average score."""
        result = run_anomaly_evals()

        assert result.average_score >= 0.70, (
            f"Anomaly avg score too low: {result.average_score:.2f}"
        )


class TestSQLEvals:
    """Test text-to-SQL evaluations."""

    def test_sql_evals_pass(self):
        """
        Test that text-to-SQL evals meet target pass rate.

        Target: ≥85% pass rate across 15 scenarios.

        Evaluates:
        - SELECT statement presence
        - tenant_id filter (security)
        - Time-based filtering
        - GROUP BY for aggregations
        - ORDER BY for rankings
        """
        result = run_sql_evals()

        assert result.target_met, (
            f"SQL evals failed: {result.pass_rate:.1%} pass rate "
            f"(target: {result.target_pass_rate:.1%}). "
            f"Passed: {result.passed_scenarios}/{result.total_scenarios}"
        )

    def test_sql_evals_security_filter(self):
        """Test that generated SQL includes tenant_id filter."""
        result = run_sql_evals()

        for eval_result in result.results:
            assert eval_result.checks.get("tenant_id") is True, (
                f"SQL scenario {eval_result.scenario_id} missing tenant_id filter"
            )


class TestNarrativeEvals:
    """Test BI narrative evaluations."""

    def test_narrative_evals_pass(self):
        """
        Test that BI narrative evals meet target pass rate.

        Target: ≥75% pass rate across 10 scenarios.

        Evaluates:
        - Specific numbers mentioned
        - Time period context
        - Tone appropriateness
        - Action recommendations
        - Sentence length
        """
        result = run_narrative_evals()

        assert result.target_met, (
            f"Narrative evals failed: {result.pass_rate:.1%} pass rate "
            f"(target: {result.target_pass_rate:.1%}). "
            f"Passed: {result.passed_scenarios}/{result.total_scenarios}"
        )

    def test_narrative_tone_appropriate(self):
        """Test that narrative tone matches data urgency."""
        result = run_narrative_evals()

        # Check urgent scenarios have urgent tone
        urgent_passed = 0
        urgent_total = 0

        for eval_result in result.results:
            if "narrative_003" in eval_result.scenario_id or "narrative_006" in eval_result.scenario_id:
                urgent_total += 1
                if eval_result.passed:
                    urgent_passed += 1

        if urgent_total > 0:
            assert urgent_passed / urgent_total >= 0.5, (
                f"Urgent narratives not appropriately toned: {urgent_passed}/{urgent_total}"
            )


class TestOverallEvals:
    """Test overall evaluation suite."""

    def test_all_evals_combined(self):
        """
        Test that all eval sets pass their targets.

        This is the main CI gate for LLM quality.
        """
        anomaly = run_anomaly_evals()
        sql = run_sql_evals()
        narrative = run_narrative_evals()

        all_passed = anomaly.target_met and sql.target_met and narrative.target_met

        assert all_passed, (
            f"Not all evals passed:\n"
            f"  Anomaly: {anomaly.pass_rate:.1%} (target: {anomaly.target_pass_rate:.1%})\n"
            f"  SQL: {sql.pass_rate:.1%} (target: {sql.target_pass_rate:.1%})\n"
            f"  Narrative: {narrative.pass_rate:.1%} (target: {narrative.target_pass_rate:.1%})"
        )

    def test_overall_average_score(self):
        """Test that overall average score is acceptable."""
        anomaly = run_anomaly_evals()
        sql = run_sql_evals()
        narrative = run_narrative_evals()

        overall_avg = (anomaly.average_score + sql.average_score + narrative.average_score) / 3

        assert overall_avg >= 0.75, (
            f"Overall average score too low: {overall_avg:.2f}"
        )
