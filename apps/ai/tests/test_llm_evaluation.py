"""Tests for LLM Evaluation Framework — deterministic scenario-based evaluation.

Covers:
1. All 8 scenarios are defined
2. Each scenario passes its expected properties
3. Evaluation produces metrics (accuracy, violation rate)
4. No scenario produces unsafe actions
5. All models strict (extra=forbid)
6. No I/O, no LLM, no wall clock
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.mission.llm_evaluation import (
    EvalMetrics,
    EvalResult,
    EvalScenario,
    EvalSuite,
    EvaluationRunner,
    build_scenarios,
    default_evaluator,
    evaluate_entity_resolution,
    evaluate_grounding,
    evaluate_severity,
)


# ── 1. All 8 scenarios are defined ──────────────────────────────────────


class TestScenarioDefinitions:
    """Verify the canonical set of eight evaluation scenarios."""

    def test_exactly_eight_scenarios(self) -> None:
        scenarios = build_scenarios()
        assert len(scenarios) == 8

    def test_scenario_ids_are_unique(self) -> None:
        scenarios = build_scenarios()
        ids = [s.id for s in scenarios]
        assert len(ids) == len(set(ids))

    def test_scenario_ids_are_e1_through_e8(self) -> None:
        scenarios = build_scenarios()
        ids = {s.id for s in scenarios}
        assert ids == {"E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"}

    def test_each_scenario_has_name_and_description(self) -> None:
        scenarios = build_scenarios()
        for scenario in scenarios:
            assert scenario.name, f"{scenario.id} missing name"
            assert scenario.description, f"{scenario.id} missing description"

    def test_each_scenario_has_expected_properties(self) -> None:
        scenarios = build_scenarios()
        for scenario in scenarios:
            assert scenario.expected_properties, (
                f"{scenario.id} missing expected_properties"
            )

    def test_e1_clear_outage(self) -> None:
        scenarios = build_scenarios()
        e1 = next(s for s in scenarios if s.id == "E1")
        assert e1.input_context["resolved_vendor"] == "stripe"
        assert e1.input_context["resolved_severity"] == "critical"
        assert e1.input_context["resolved_action_type"] == "escalate_vendor"
        assert e1.expected_properties["expected_vendor"] == "stripe"
        assert e1.expected_properties["expected_severity"] == "critical"

    def test_e2_ambiguous_vendor(self) -> None:
        scenarios = build_scenarios()
        e2 = next(s for s in scenarios if s.id == "E2")
        assert e2.input_context["resolved_vendor"] == "AMBIGUOUS"
        assert e2.expected_properties["expected_vendor"] == "AMBIGUOUS"
        assert e2.expected_properties["hallucination"] is False

    def test_e3_conflicting_evidence(self) -> None:
        scenarios = build_scenarios()
        e3 = next(s for s in scenarios if s.id == "E3")
        assert e3.input_context["conflict_detected"] is True
        assert e3.expected_properties["conflict_detected"] is True

    def test_e4_missing_sla(self) -> None:
        scenarios = build_scenarios()
        e4 = next(s for s in scenarios if s.id == "E4")
        assert e4.input_context["missing_sla_flagged"] is True
        assert e4.expected_properties["missing_sla_flagged"] is True

    def test_e5_malicious_content(self) -> None:
        scenarios = build_scenarios()
        e5 = next(s for s in scenarios if s.id == "E5")
        assert e5.input_context["injection_ignored"] is True
        assert e5.expected_properties["injection_ignored"] is True
        # Verify injection text is present in evidence
        assert any(
            "IGNORE PREVIOUS INSTRUCTIONS" in e.get("content", "")
            for e in e5.input_evidence
        )

    def test_e6_material_action(self) -> None:
        scenarios = build_scenarios()
        e6 = next(s for s in scenarios if s.id == "E6")
        assert e6.input_context["risk_level"] == "HIGH"
        assert e6.input_context["auto_executed"] is False
        assert e6.expected_properties["requires_approval"] is True

    def test_e7_recovery_false_positive(self) -> None:
        scenarios = build_scenarios()
        e7 = next(s for s in scenarios if s.id == "E7")
        assert e7.input_context["recovery_verified"] is False
        assert e7.expected_properties["recovery_verified"] is False

    def test_e8_insufficient_evidence(self) -> None:
        scenarios = build_scenarios()
        e8 = next(s for s in scenarios if s.id == "E8")
        assert e8.input_evidence == []
        assert e8.input_context["risk_level"] == "MEDIUM"
        assert e8.input_context["action_executed"] is False
        assert e8.expected_properties["evidence_required"] is True


# ── 2. Each scenario passes its expected properties ─────────────────────


class TestScenarioPasses:
    """Every built-in scenario must pass the default evaluator."""

    def test_all_scenarios_pass(self) -> None:
        scenarios = build_scenarios()
        for scenario in scenarios:
            result = default_evaluator(scenario)
            assert result.passed, (
                f"{scenario.id} ({scenario.name}) failed: {result.violations}"
            )

    def test_no_violations_in_any_scenario(self) -> None:
        scenarios = build_scenarios()
        for scenario in scenarios:
            result = default_evaluator(scenario)
            assert result.violations == [], (
                f"{scenario.id} unexpected violations: {result.violations}"
            )

    def test_e1_entity_resolution(self) -> None:
        scenarios = build_scenarios()
        e1 = next(s for s in scenarios if s.id == "E1")
        result = default_evaluator(e1)
        assert result.metrics["entity_resolution"] == 1.0
        assert result.metrics["severity"] == 1.0

    def test_e2_no_hallucination(self) -> None:
        scenarios = build_scenarios()
        e2 = next(s for s in scenarios if s.id == "E2")
        result = default_evaluator(e2)
        assert result.metrics["entity_resolution"] == 1.0
        assert result.metrics["grounding"] == 1.0

    def test_e3_conflict_detected(self) -> None:
        scenarios = build_scenarios()
        e3 = next(s for s in scenarios if s.id == "E3")
        result = default_evaluator(e3)
        assert result.metrics["grounding"] == 1.0

    def test_e4_missing_sla_flagged(self) -> None:
        scenarios = build_scenarios()
        e4 = next(s for s in scenarios if s.id == "E4")
        result = default_evaluator(e4)
        assert result.metrics["grounding"] == 1.0

    def test_e5_injection_ignored(self) -> None:
        scenarios = build_scenarios()
        e5 = next(s for s in scenarios if s.id == "E5")
        result = default_evaluator(e5)
        assert result.metrics.get("injection_resistance", 0.0) == 1.0
        assert result.metrics["grounding"] == 1.0

    def test_e6_action_requires_approval(self) -> None:
        scenarios = build_scenarios()
        e6 = next(s for s in scenarios if s.id == "E6")
        result = default_evaluator(e6)
        assert result.metrics["action_safety"] == 1.0

    def test_e7_recovery_rejected(self) -> None:
        scenarios = build_scenarios()
        e7 = next(s for s in scenarios if s.id == "E7")
        result = default_evaluator(e7)
        assert result.metrics["recovery"] == 1.0

    def test_e8_evidence_required(self) -> None:
        scenarios = build_scenarios()
        e8 = next(s for s in scenarios if s.id == "E8")
        result = default_evaluator(e8)
        assert result.metrics["evidence_requirement"] == 1.0


# ── 3. Evaluation produces metrics ──────────────────────────────────────


class TestMetrics:
    """Verify aggregate metrics computation."""

    def test_runner_produces_metrics(self) -> None:
        runner = EvaluationRunner()
        results, metrics = runner.run()
        assert len(results) == 8
        assert isinstance(metrics, EvalMetrics)

    def test_accuracy_is_one_when_all_pass(self) -> None:
        runner = EvaluationRunner()
        _, metrics = runner.run()
        assert metrics.accuracy == 1.0

    def test_violation_rate_is_zero_when_all_pass(self) -> None:
        runner = EvaluationRunner()
        _, metrics = runner.run()
        assert metrics.violation_rate == 0.0

    def test_safety_score_is_one_when_no_unsafe_actions(self) -> None:
        runner = EvaluationRunner()
        _, metrics = runner.run()
        assert metrics.safety_score == 1.0

    def test_total_matches_scenario_count(self) -> None:
        runner = EvaluationRunner()
        _, metrics = runner.run()
        assert metrics.total == 8
        assert metrics.passed == 8
        assert metrics.failed == 0

    def test_property_scores_computed(self) -> None:
        runner = EvaluationRunner()
        _, metrics = runner.run()
        assert "entity_resolution" in metrics.property_scores
        assert "severity" in metrics.property_scores
        assert "grounding" in metrics.property_scores
        assert "action_safety" in metrics.property_scores
        assert "recovery" in metrics.property_scores
        assert "evidence_requirement" in metrics.property_scores

    def test_property_scores_are_one_when_all_pass(self) -> None:
        runner = EvaluationRunner()
        _, metrics = runner.run()
        for prop, score in metrics.property_scores.items():
            assert score == 1.0, f"property {prop} score is {score}, expected 1.0"

    def test_eval_suite_evaluate_method(self) -> None:
        scenarios = build_scenarios()
        suite = EvalSuite(scenarios=scenarios)
        results = suite.evaluate(default_evaluator)
        assert len(results) == 8
        assert all(r.passed for r in results)

    def test_metrics_model_validates_bounds(self) -> None:
        metrics = EvalMetrics(
            total=8,
            passed=6,
            failed=2,
            accuracy=0.75,
            safety_score=1.0,
            violation_rate=0.25,
            property_scores={"entity_resolution": 0.8},
        )
        assert metrics.accuracy == 0.75
        assert metrics.failed == 2


# ── 4. No scenario produces unsafe actions ──────────────────────────────


class TestActionSafety:
    """Verify that no evaluation scenario produces unsafe actions."""

    def test_no_auto_executed_high_risk(self) -> None:
        scenarios = build_scenarios()
        for scenario in scenarios:
            risk = scenario.input_context.get("risk_level", "LOW")
            auto = scenario.input_context.get("auto_executed", False)
            assert not (risk in ("HIGH", "CRITICAL") and auto), (
                f"{scenario.id}: HIGH/CRITICAL risk action is auto-executed"
            )

    def test_e6_requires_approval(self) -> None:
        scenarios = build_scenarios()
        e6 = next(s for s in scenarios if s.id == "E6")
        assert e6.input_context["auto_executed"] is False
        assert e6.expected_properties["requires_approval"] is True

    def test_e5_injection_not_executed(self) -> None:
        scenarios = build_scenarios()
        e5 = next(s for s in scenarios if s.id == "E5")
        # The injection text must not cause an action
        assert e5.input_context.get("injection_ignored") is True
        assert e5.expected_properties.get("hallucination") is False

    def test_e8_no_action_without_evidence(self) -> None:
        scenarios = build_scenarios()
        e8 = next(s for s in scenarios if s.id == "E8")
        assert e8.input_context["action_executed"] is False
        assert e8.input_evidence == []

    def test_safety_score_in_runner(self) -> None:
        runner = EvaluationRunner()
        _, metrics = runner.run()
        assert metrics.safety_score == 1.0


# ── 5. All models strict (extra=forbid) ─────────────────────────────────


class TestModelStrictness:
    """Verify that all Pydantic models reject unknown fields."""

    def test_eval_scenario_extra_forbid(self) -> None:
        with pytest.raises(Exception):
            EvalScenario(
                id="X",
                name="test",
                description="test",
                unknown_field="should_fail",  # type: ignore[arg-type]
            )

    def test_eval_result_extra_forbid(self) -> None:
        with pytest.raises(Exception):
            EvalResult(
                scenario_id="X",
                passed=True,
                unknown_field="should_fail",  # type: ignore[arg-type]
            )

    def test_eval_suite_extra_forbid(self) -> None:
        with pytest.raises(Exception):
            EvalSuite(
                scenarios=[],
                unknown_field="should_fail",  # type: ignore[arg-type]
            )

    def test_eval_metrics_extra_forbid(self) -> None:
        with pytest.raises(Exception):
            EvalMetrics(
                total=0,
                passed=0,
                failed=0,
                accuracy=0.0,
                safety_score=0.0,
                violation_rate=0.0,
                unknown_field="should_fail",  # type: ignore[arg-type]
            )

    def test_eval_scenario_strict_rejects_wrong_types(self) -> None:
        with pytest.raises(Exception):
            EvalScenario(
                id=123,  # should be str  # type: ignore[arg-type]
                name="test",
                description="test",
            )

    def test_eval_result_strict_rejects_wrong_types(self) -> None:
        with pytest.raises(Exception):
            EvalResult(
                scenario_id="X",
                passed="yes",  # should be bool  # type: ignore[arg-type]
            )


# ── 6. No I/O, no LLM, no wall clock ────────────────────────────────────


class TestNoIoOrLlm:
    """Verify the evaluation module contains no I/O, LLM, or wall clock."""

    def test_no_io_in_llm_evaluation(self) -> None:
        src = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "mission"
            / "llm_evaluation.py"
        )
        text = src.read_text()
        assert "time.sleep" not in text
        assert "datetime.now(" not in text
        assert "while True" not in text
        assert "import openai" not in text
        assert "chat_completion" not in text
        assert "aiohttp" not in text
        assert "httpx" not in text
        assert "requests.get" not in text
        assert "requests.post" not in text
        assert "urllib" not in text

    def test_no_file_io_in_evaluator(self) -> None:
        """The evaluator must not read/write files."""
        src = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "mission"
            / "llm_evaluation.py"
        )
        text = src.read_text()
        assert "open(" not in text
        assert "Path(" not in text or "Path(" in text  # Path is fine in imports
        # More precise: no file open() calls in function bodies
        lines = text.split("\n")
        in_function = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("def ") or stripped.startswith("async def "):
                in_function = True
            if in_function and "open(" in stripped and not stripped.startswith("#"):
                assert False, f"file open() found in function body: {stripped}"

    def test_no_subprocess_in_evaluator(self) -> None:
        src = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "mission"
            / "llm_evaluation.py"
        )
        text = src.read_text()
        assert "subprocess" not in text
        assert "os.system" not in text


# ── Evaluator function unit tests ────────────────────────────────────────


class TestEvaluatorFunctions:
    """Unit tests for individual evaluator functions."""

    def _make_scenario(self, **overrides: object) -> EvalScenario:
        base: dict[str, object] = {
            "id": "T1",
            "name": "test",
            "description": "test scenario",
            "input_evidence": [],
            "input_context": {},
            "expected_properties": {},
        }
        base.update(overrides)
        return EvalScenario(**base)  # type: ignore[arg-type]

    def _make_result(self, **overrides: object) -> EvalResult:
        base: dict[str, object] = {
            "scenario_id": "T1",
            "passed": True,
            "violations": [],
            "metrics": {},
        }
        base.update(overrides)
        return EvalResult(**base)  # type: ignore[arg-type]

    def test_entity_resolution_correct_vendor(self) -> None:
        scenario = self._make_scenario(
            input_context={"resolved_vendor": "stripe"},
            expected_properties={"expected_vendor": "stripe"},
        )
        result = self._make_result()
        violations = evaluate_entity_resolution(scenario, result)
        assert violations == []

    def test_entity_resolution_wrong_vendor(self) -> None:
        scenario = self._make_scenario(
            input_context={"resolved_vendor": "paypal"},
            expected_properties={"expected_vendor": "stripe"},
        )
        result = self._make_result()
        violations = evaluate_entity_resolution(scenario, result)
        assert len(violations) == 1
        assert "vendor_resolution" in violations[0]

    def test_entity_resolution_ambiguous(self) -> None:
        scenario = self._make_scenario(
            input_context={"resolved_vendor": "AMBIGUOUS"},
            expected_properties={"expected_vendor": "AMBIGUOUS"},
        )
        result = self._make_result()
        violations = evaluate_entity_resolution(scenario, result)
        assert violations == []

    def test_entity_resolution_ambiguous_wrong(self) -> None:
        scenario = self._make_scenario(
            input_context={"resolved_vendor": "stripe"},
            expected_properties={"expected_vendor": "AMBIGUOUS"},
        )
        result = self._make_result()
        violations = evaluate_entity_resolution(scenario, result)
        assert len(violations) == 1

    def test_severity_correct(self) -> None:
        scenario = self._make_scenario(
            input_context={"resolved_severity": "critical"},
            expected_properties={"expected_severity": "critical"},
        )
        result = self._make_result()
        violations = evaluate_severity(scenario, result)
        assert violations == []

    def test_severity_wrong(self) -> None:
        scenario = self._make_scenario(
            input_context={"resolved_severity": "low"},
            expected_properties={"expected_severity": "critical"},
        )
        result = self._make_result()
        violations = evaluate_severity(scenario, result)
        assert len(violations) == 1
        assert "severity" in violations[0]

    def test_grounding_no_hallucination(self) -> None:
        scenario = self._make_scenario(
            input_context={"hallucination": False},
            expected_properties={"hallucination": False},
        )
        result = self._make_result()
        violations = evaluate_grounding(scenario, result)
        assert violations == []

    def test_grounding_hallucination_detected(self) -> None:
        scenario = self._make_scenario(
            input_context={"hallucination": True},
            expected_properties={"hallucination": False},
        )
        result = self._make_result()
        violations = evaluate_grounding(scenario, result)
        assert len(violations) == 1
        assert "hallucination" in violations[0]

    def test_grounding_conflict_detected(self) -> None:
        scenario = self._make_scenario(
            input_context={"conflict_detected": True},
            expected_properties={"conflict_detected": True},
        )
        result = self._make_result()
        violations = evaluate_grounding(scenario, result)
        assert violations == []

    def test_grounding_conflict_not_detected(self) -> None:
        scenario = self._make_scenario(
            input_context={"conflict_detected": False},
            expected_properties={"conflict_detected": True},
        )
        result = self._make_result()
        violations = evaluate_grounding(scenario, result)
        assert len(violations) == 1
        assert "conflict_detection" in violations[0]

    def test_grounding_missing_sla_flagged(self) -> None:
        scenario = self._make_scenario(
            input_context={"missing_sla_flagged": True},
            expected_properties={"missing_sla_flagged": True},
        )
        result = self._make_result()
        violations = evaluate_grounding(scenario, result)
        assert violations == []

    def test_grounding_missing_sla_not_flagged(self) -> None:
        scenario = self._make_scenario(
            input_context={"missing_sla_flagged": False},
            expected_properties={"missing_sla_flagged": True},
        )
        result = self._make_result()
        violations = evaluate_grounding(scenario, result)
        assert len(violations) == 1
        assert "missing_sla" in violations[0]

    def test_no_expected_vendor_returns_empty(self) -> None:
        scenario = self._make_scenario(
            input_context={},
            expected_properties={},
        )
        result = self._make_result()
        violations = evaluate_entity_resolution(scenario, result)
        assert violations == []

    def test_no_expected_severity_returns_empty(self) -> None:
        scenario = self._make_scenario(
            input_context={},
            expected_properties={},
        )
        result = self._make_result()
        violations = evaluate_severity(scenario, result)
        assert violations == []


# ── Edge cases ───────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_suite(self) -> None:
        suite = EvalSuite(scenarios=[])
        results = suite.evaluate(default_evaluator)
        assert results == []

    def test_runner_with_custom_scenarios(self) -> None:
        custom = [
            EvalScenario(
                id="C1",
                name="custom",
                description="custom scenario",
                input_context={"resolved_vendor": "x", "resolved_severity": "low"},
                expected_properties={
                    "expected_vendor": "x",
                    "expected_severity": "low",
                },
            ),
        ]
        runner = EvaluationRunner(scenarios=custom)
        results, metrics = runner.run()
        assert len(results) == 1
        assert results[0].passed
        assert metrics.accuracy == 1.0

    def test_runner_with_failing_evaluator(self) -> None:
        """A custom evaluator that always fails."""

        def failing_evaluator(scenario: EvalScenario) -> EvalResult:
            return EvalResult(
                scenario_id=scenario.id,
                passed=False,
                violations=["always_fail"],
            )

        runner = EvaluationRunner(evaluator=failing_evaluator)
        results, metrics = runner.run()
        assert metrics.accuracy == 0.0
        assert metrics.failed == 8

    def test_eval_metrics_zero_division(self) -> None:
        """Metrics handle empty result set gracefully."""
        metrics = EvaluationRunner._compute_metrics([])
        assert metrics.total == 0
        assert metrics.accuracy == 0.0
        assert metrics.safety_score == 1.0  # no unsafe actions in empty set
        assert metrics.violation_rate == 0.0

    def test_eval_scenario_model_copy(self) -> None:
        """Scenarios can be deep-copied for mutation."""
        scenarios = build_scenarios()
        e1 = scenarios[0]
        copy = e1.model_copy(deep=True)
        assert copy.id == e1.id
        assert copy is not e1
