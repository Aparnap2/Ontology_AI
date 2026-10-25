"""Regression contracts for the deterministic eval evaluators."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evals.datasets.bi_narratives import NarrativeEvalScenario, evaluate_narrative_output
from evals.datasets.criteria import criterion_matches
from evals.datasets.text_to_sql import SQLEvalScenario, evaluate_sql_output


class TestCriterionMatching:
    def test_numeric_ratio_uses_pair_of_values(self):
        text = "Spend was $7,500 versus the $5,000 average."
        assert criterion_matches("mentions 1.5x or 50% increase", text) is True

    def test_absent_ratio_fails(self):
        text = "Spend was $7,500 versus the $5,000 average."
        assert criterion_matches("mentions 3x", text) is False

    def test_month_unit_is_not_parsed_as_millions(self):
        text = "Runway is only 1.8 months and below the 3 month threshold."
        assert criterion_matches("mentions runway < 2 months", text) is True

    def test_optional_criteria_are_excluded(self):
        assert criterion_matches("may mention industry benchmark", "No benchmark.") is None

    def test_negative_alarm_criterion_rejects_critical_text(self):
        assert criterion_matches("no unnecessary alarm or urgency", "CRITICAL: act now.") is False
        assert criterion_matches("no unnecessary alarm or urgency", "Routine transaction.") is True

    def test_action_verification_aliases(self):
        text = "Please verify this expense with finance."
        assert criterion_matches("recommends immediate verification", text) is True


class TestSQLEvaluator:
    def _scenario(self) -> SQLEvalScenario:
        return SQLEvalScenario(
            id="contract_sql",
            nl_query="Show total revenue last 30 days",
            gold_sql_pattern=(
                "SELECT SUM(credit) FROM transactions "
                "WHERE txn_date >= NOW() - INTERVAL '30 days'"
            ),
            expected_columns=["sum"],
            time_hint="last 30 days",
            difficulty="easy",
            query_category="aggregation",
        )

    def test_tenant_filter_is_a_required_check(self):
        result = evaluate_sql_output(
            "SELECT SUM(credit) FROM transactions WHERE txn_date >= NOW() - INTERVAL '30 days'",
            self._scenario(),
        )
        assert result["checks"]["tenant_id"] is False
        assert result["passed"] is False
        assert any("tenant_id" in reason for reason in result["reasons"])

    def test_tenant_filter_marks_check_true(self):
        result = evaluate_sql_output(
            "SELECT SUM(credit) FROM transactions "
            "WHERE tenant_id = 't1' AND txn_date >= NOW() - INTERVAL '30 days'",
            self._scenario(),
        )
        assert result["checks"]["tenant_id"] is True
        assert result["passed"] is True

    def test_time_filter_is_not_required_when_gold_has_none(self):
        scenario = SQLEvalScenario(
            id="contract_no_time",
            nl_query="How many months of runway do I have",
            gold_sql_pattern=(
                "SELECT runway_months FROM finance_snapshots "
                "ORDER BY snapshot_date DESC LIMIT 1"
            ),
            expected_columns=["runway_months"],
            time_hint="current",
            difficulty="easy",
            query_category="aggregation",
        )
        result = evaluate_sql_output(
            "SELECT runway_months FROM finance_snapshots "
            "WHERE tenant_id = 't1' ORDER BY snapshot_date DESC LIMIT 1",
            scenario,
        )
        assert "time_filter" not in result["checks"]
        assert result["passed"] is True


class TestNarrativeEvaluator:
    def _scenario(self) -> NarrativeEvalScenario:
        return NarrativeEvalScenario(
            id="contract_narrative",
            sql_result={"rows": [{"sum": 150000.0}], "columns": ["sum"], "count": 1},
            query_context="Show total revenue last 30 days",
            gold_criteria=[
                "mentions specific amount $150,000",
                "mentions revenue",
                "no unnecessary alarm or urgency",
            ],
            expected_tone="informative",
            min_sentences=1,
            max_sentences=3,
        )

    def test_informative_narrative_passes_with_evidence(self):
        result = evaluate_narrative_output(
            "Your revenue for the last 30 days is $150,000. Review the breakdown for details.",
            self._scenario(),
        )
        assert result["passed"] is True
        assert result["score"] >= 0.7

    def test_urgent_language_costs_informative_narrative(self):
        result = evaluate_narrative_output(
            "CRITICAL: revenue is down. Act now.",
            self._scenario(),
        )
        assert result["passed"] is False
        assert any("alarm" in reason.lower() for reason in result["reasons"])


class TestEvaluatorDefectRegression:
    """Regression tests for A1, A3, A4, A5, A6 evaluator defects."""

    # A1: SQL rubric weighting — single-column aggregation must reach 0.70
    def test_sql_single_column_aggregation_reaches_threshold(self):
        from evals.datasets.text_to_sql import SQLEvalScenario, evaluate_sql_output
        scenario = SQLEvalScenario(
            id="reg_sql_agg",
            nl_query="Show total revenue last 30 days",
            gold_sql_pattern="SELECT SUM(credit) FROM transactions WHERE txn_date >= NOW() - INTERVAL '30 days'",
            expected_columns=["sum"],
            time_hint="last 30 days",
            difficulty="easy",
            query_category="aggregation",
        )
        result = evaluate_sql_output(
            "SELECT SUM(credit) FROM transactions WHERE tenant_id = 't1' AND txn_date >= NOW() - INTERVAL '30 days'",
            scenario,
        )
        assert result["score"] >= 0.70, f"SQL score {result['score']} below 0.70 for single-column aggregation"
        assert result["passed"] is True

    # A4: reasons must be consistent with score/passed
    def test_sql_reasons_consistent_with_score(self):
        from evals.datasets.text_to_sql import SQLEvalScenario, evaluate_sql_output
        scenario = SQLEvalScenario(
            id="reg_sql_consistent",
            nl_query="Show total revenue last 30 days",
            gold_sql_pattern="SELECT SUM(credit) FROM transactions WHERE txn_date >= NOW() - INTERVAL '30 days'",
            expected_columns=["sum"],
            time_hint="last 30 days",
            difficulty="easy",
            query_category="aggregation",
        )
        result = evaluate_sql_output(
            "SELECT SUM(credit) FROM transactions WHERE tenant_id = 't1' AND txn_date >= NOW() - INTERVAL '30 days'",
            scenario,
        )
        if result["passed"]:
            # Should not say "below pass threshold" if passed
            assert not any("below pass threshold" in r for r in result["reasons"]), \
                f"Passed but reasons mention below threshold: {result['reasons']}"
        else:
            assert any("below pass threshold" in r for r in result["reasons"]), \
                f"Failed but reasons don't mention below threshold: {result['reasons']}"

    # A5: Narrative neutral tone must receive tone score
    def test_narrative_neutral_tone_gets_score(self):
        from evals.datasets.bi_narratives import NarrativeEvalScenario, evaluate_narrative_output
        scenario = NarrativeEvalScenario(
            id="reg_narrative_neutral",
            sql_result={"rows": [{"runway_months": 14.5}], "columns": ["runway_months"], "count": 1},
            query_context="How many months of runway do I have",
            gold_criteria=["mentions specific runway (14.5 months)"],
            expected_tone="neutral",
            min_sentences=1,
            max_sentences=3,
        )
        result = evaluate_narrative_output(
            "Your runway is 14.5 months. This is a healthy position.",
            scenario,
        )
        # Neutral tone with no alarm words should get +0.15 tone score
        # Score should be at least 0.35 (0.2 sentence + 0.15 tone)
        assert result["score"] >= 0.35, f"Neutral tone score {result['score']} too low (expected >= 0.35)"

    # A6: Negative criteria must not match on forbidden words
    def test_negative_criterion_rejects_alarm_text(self):
        from evals.datasets.criteria import criterion_matches
        # A narrative saying "alarm" should FAIL the "no unnecessary alarm" criterion
        assert criterion_matches("no unnecessary alarm or urgency", "Your revenue is $150,000. CRITICAL: act now!") is False
        assert criterion_matches("no unnecessary alarm or urgency", "Your revenue is $150,000. This is an alarm situation.") is False

    def test_negative_criterion_passes_clean_text(self):
        from evals.datasets.criteria import criterion_matches
        assert criterion_matches("no unnecessary alarm or urgency", "Your revenue is $150,000. Review the breakdown.") is True

    # A3: Anomaly generic keyword branch must append reason on miss
    def test_anomaly_reasons_include_missing_criteria(self):
        from evals.run_evals import _evaluate_anomaly_explanation
        from evals.datasets.anomaly_explanations import get_anomaly_eval_scenarios
        scenarios = get_anomaly_eval_scenarios()
        # Find a scenario that will fail
        for scenario in scenarios:
            result = _evaluate_anomaly_explanation("Routine transaction. No action needed.", scenario)
            if not result.passed:
                # Reasons should include missing criteria, not be empty
                assert len(result.reasons) > 0, f"Empty reasons for failed scenario {scenario.id}"
                assert any("Missing" in r or "below pass threshold" in r for r in result.reasons), \
                    f"No missing/threshold reason for {scenario.id}: {result.reasons}"
                break
