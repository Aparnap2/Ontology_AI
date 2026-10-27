"""Regression contracts for the deterministic eval evaluators."""
import os
import sys

import pytest

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


class TestAnomalyScoringContracts:
    """Owner decision #102 / A2 — anomaly explanation scoring contract.

    * optional criteria (matcher returns ``None``) are excluded from scoring,
      never counted as failures and never raise;
    * required criteria with a supported matcher path are scored normally;
    * required criteria with no supported matcher path are REJECTED and
      FLAGGED — never silently omitted from the denominator;
    * negative criteria ("no ...") must be scored by the matcher, not
      misclassified as unscorable (regression pin for the verb-gate bug).
    """

    @staticmethod
    def _scenario(gold_criteria, expected_action="ALERT"):
        from evals.datasets.anomaly_explanations import AnomalyEvalScenario

        return AnomalyEvalScenario(
            id="a2-contract",
            event_type="payment.success",
            vendor="aws",
            amount=10000.0,
            avg_90d=5000.0,
            anomaly_score=0.7,
            runway_months=12.0,
            past_context="No similar anomalies in past 90 days",
            gold_criteria=gold_criteria,
            expected_action=expected_action,
        )

    @staticmethod
    def _evaluate(explanation, gold_criteria, expected_action="ALERT"):
        from evals.run_evals import _evaluate_anomaly_explanation

        return _evaluate_anomaly_explanation(
            explanation,
            TestAnomalyScoringContracts._scenario(gold_criteria, expected_action),
        )

    def test_optional_criterion_excluded_without_error(self):
        criteria = [
            "mentions aws payment.success",  # required, supported
            "may mention industry benchmark",  # optional -> matcher returns None
        ]
        explanation = "Alert: aws payment.success spike of 2x vs 90d average."
        result = self._evaluate(explanation, criteria)

        # Optional criterion is excluded from the checks map entirely.
        assert "criterion_1" not in result.checks
        # ...and never produces a failure reason of any kind.
        assert not any("benchmark" in reason for reason in result.reasons)
        assert not any("Unscorable" in reason for reason in result.reasons)
        # Required criterion still scores normally.
        assert result.checks["criterion_0"] is True

    def test_unsupported_required_criterion_rejected_and_flagged(self):
        criteria = [
            "mentions aws payment.success",  # supported
            "references past similar event",  # no supported matcher path
        ]
        explanation = "Alert: aws payment.success spike of 2x vs 90d average."
        result = self._evaluate(explanation, criteria)

        # Flagged as False and reported — not silently dropped.
        assert result.checks.get("criterion_1") is False
        assert any(
            "Unscorable criterion" in reason for reason in result.reasons
        )
        assert any(
            "references past similar event" in reason for reason in result.reasons
        )
        # The flagged criterion counts in the denominator: one of two matched.
        # score = 0.9 * (1/2) + action bonus (Alert present) = 0.55 < 0.60
        assert result.passed is False
        assert result.score == pytest.approx(0.55)

    def test_negative_criterion_is_scored_not_flagged(self):
        """Regression pin: negative criteria have a matcher path and must not
        be misclassified as unscorable (the verb-gate regression)."""
        criteria = ["no alarm language"]
        explanation = "Brief summary: aws payment processed normally."
        result = self._evaluate(explanation, criteria, expected_action="DIGEST")

        assert result.checks["criterion_0"] is True
        assert not any("Unscorable" in reason for reason in result.reasons)
        assert not any("Missing" in reason for reason in result.reasons)

    def test_negative_criterion_fails_when_forbidden_words_present(self):
        """Negative criteria are actually scored — they can fail too."""
        criteria = ["no alarm language"]
        explanation = "Alert: critical alarm on aws payment failure."
        result = self._evaluate(explanation, criteria, expected_action="ALERT")

        assert result.checks["criterion_0"] is False
        assert not any("Unscorable" in reason for reason in result.reasons)
        assert any("Missing" in reason for reason in result.reasons)

    def test_supported_verb_criterion_scored_normally(self):
        criteria = ["mentions aws"]
        explanation = "Alert: aws charge doubled today."
        result = self._evaluate(explanation, criteria)

        assert result.checks["criterion_0"] is True
        assert not any("Unscorable" in reason for reason in result.reasons)
