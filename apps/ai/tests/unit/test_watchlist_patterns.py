"""Tests for Guardian Watchlist Pattern Detection — TDD.

Tests each of 17 watchlist patterns (FG-01 to FG-06, BG-01 to BG-06, OG-01 to OG-05).
"""
import pytest
from src.guardian.detector import GuardianDetector


class TestFinancePatterns:
    """FG-01 to FG-06: Finance domain patterns."""

    @pytest.fixture
    def detector(self):
        return GuardianDetector()

    def test_fg01_detects_silent_churn_death(self, detector):
        """FG-01: Silent Churn Death - >3% monthly churn triggers."""
        signals = {"monthly_churn_pct": 0.04}
        matched = detector.run(signals)
        assert any(p.id == "FG-01" for p in matched)

    def test_fg01_no_false_positive(self, detector):
        """FG-01: <3% monthly churn should NOT trigger."""
        signals = {"monthly_churn_pct": 0.02}
        matched = detector.run(signals)
        assert not any(p.id == "FG-01" for p in matched)

    def test_fg02_detects_burn_multiple_creep(self, detector):
        """FG-02: Burn multiple >2x triggers."""
        signals = {"net_burn": 20000, "net_new_arr": 8000}
        matched = detector.run(signals)
        assert any(p.id == "FG-02" for p in matched)

    def test_fg02_no_false_positive(self, detector):
        """FG-02: Burn multiple <=2x should NOT trigger."""
        signals = {"net_burn": 10000, "net_new_arr": 8000}
        matched = detector.run(signals)
        assert not any(p.id == "FG-02" for p in matched)

    def test_fg03_detects_customer_concentration(self, detector):
        """FG-03: Single customer >30% MRR triggers."""
        signals = {"top_customer_mrr": 3500, "total_mrr": 10000}
        matched = detector.run(signals)
        assert any(p.id == "FG-03" for p in matched)

    def test_fg03_no_false_positive(self, detector):
        """FG-03: Top customer <30% MRR should NOT trigger."""
        signals = {"top_customer_mrr": 2000, "total_mrr": 10000}
        matched = detector.run(signals)
        assert not any(p.id == "FG-03" for p in matched)

    def test_fg04_detects_runway_compression(self, detector):
        """FG-04: Runway <6 months triggers."""
        signals = {"runway_months": 4}
        matched = detector.run(signals)
        assert any(p.id == "FG-04" for p in matched)

    def test_fg04_no_false_positive(self, detector):
        """FG-04: Runway >=6 months should NOT trigger."""
        signals = {"runway_months": 10}
        matched = detector.run(signals)
        assert not any(p.id == "FG-04" for p in matched)

    def test_fg05_detects_failed_payment_cluster(self, detector):
        """FG-05: Payment failures >2% triggers."""
        signals = {"failed_payment_pct": 4.5}
        matched = detector.run(signals)
        assert any(p.id == "FG-05" for p in matched)

    def test_fg05_no_false_positive(self, detector):
        """FG-05: Payment failures <=2% should NOT trigger."""
        signals = {"failed_payment_pct": 1.5}
        matched = detector.run(signals)
        assert not any(p.id == "FG-05" for p in matched)

    def test_fg06_detects_payroll_revenue_ratio(self, detector):
        """FG-06: Payroll >60% of MRR triggers."""
        signals = {"payroll_monthly": 12000, "mrr": 18000}
        matched = detector.run(signals)
        assert any(p.id == "FG-06" for p in matched)

    def test_fg06_no_false_positive(self, detector):
        """FG-06: Payroll <=60% of MRR should NOT trigger."""
        signals = {"payroll_monthly": 8000, "mrr": 20000}
        matched = detector.run(signals)
        assert not any(p.id == "FG-06" for p in matched)


class TestBusinessInsightPatterns:
    """BG-01 to BG-06: Business Insight domain patterns."""

    @pytest.fixture
    def detector(self):
        return GuardianDetector()

    def test_bg01_detects_leaky_bucket(self, detector):
        """BG-01: Activation <40% + MRR growth = leaky bucket."""
        signals = {"new_signups": 100, "activation_rate": 30, "mrr_growth_pct": 10}
        matched = detector.run(signals)
        assert any(p.id == "BG-01" for p in matched)

    def test_bg01_no_false_positive(self, detector):
        """BG-01: Activation >=40% should NOT trigger."""
        signals = {"new_signups": 100, "activation_rate": 55, "mrr_growth_pct": 10}
        matched = detector.run(signals)
        assert not any(p.id == "BG-01" for p in matched)

    def test_bg02_detects_power_user_masking(self, detector):
        """BG-02: Top 10% >60% MRR + new customer avg <80% of all."""
        signals = {
            "top_10pct_mrr": 6500,
            "total_mrr": 10000,
            "avg_mrr_new_customers": 80,
            "avg_mrr_all_customers": 120,
        }
        matched = detector.run(signals)
        assert any(p.id == "BG-02" for p in matched)

    def test_bg02_no_false_positive(self, detector):
        """BG-02: Healthy distribution should NOT trigger."""
        signals = {
            "top_10pct_mrr": 3000,
            "total_mrr": 10000,
            "avg_mrr_new_customers": 100,
            "avg_mrr_all_customers": 120,
        }
        matched = detector.run(signals)
        assert not any(p.id == "BG-02" for p in matched)

    def test_bg03_detects_feature_adoption_drop(self, detector):
        """BG-03: Feature adoption drop post-deploy."""
        signals = {"feature_adoption_pct_before": 60, "feature_adoption_pct_after": 35}
        matched = detector.run(signals)
        assert any(p.id == "BG-03" for p in matched)

    def test_bg03_no_false_positive(self, detector):
        """BG-03: Healthy adoption should NOT trigger."""
        signals = {"feature_adoption_pct_before": 60, "feature_adoption_pct_after": 58}
        matched = detector.run(signals)
        assert not any(p.id == "BG-03" for p in matched)

    def test_bg04_detects_cohort_degradation(self, detector):
        """BG-04: Cohort retention degrades >10%."""
        signals = {"cohort_retention_current": 65, "cohort_retention_previous": 85}
        matched = detector.run(signals)
        assert any(p.id == "BG-04" for p in matched)

    def test_bg04_no_false_positive(self, detector):
        """BG-04: Healthy retention should NOT trigger."""
        signals = {"cohort_retention_current": 80, "cohort_retention_previous": 82}
        matched = detector.run(signals)
        assert not any(p.id == "BG-04" for p in matched)

    def test_bg05_detects_nrr_below_100(self, detector):
        """BG-05: NRR <100% at seed = contraction."""
        signals = {"nrr_pct": 90}
        matched = detector.run(signals)
        assert any(p.id == "BG-05" for p in matched)

    def test_bg05_no_false_positive(self, detector):
        """BG-05: NRR >=100% should NOT trigger."""
        signals = {"nrr_pct": 115}
        matched = detector.run(signals)
        assert not any(p.id == "BG-05" for p in matched)

    def test_bg06_detects_trial_activation_wall(self, detector):
        """BG-06: Trial activation <20% triggers."""
        signals = {"trial_activation_rate_pct": 12}
        matched = detector.run(signals)
        assert any(p.id == "BG-06" for p in matched)

    def test_bg06_no_false_positive(self, detector):
        """BG-06: Trial activation >=20% should NOT trigger."""
        signals = {"trial_activation_rate_pct": 30}
        matched = detector.run(signals)
        assert not any(p.id == "BG-06" for p in matched)


class TestOpsPatterns:
    """OG-01 to OG-05: Operations domain patterns."""

    @pytest.fixture
    def detector(self):
        return GuardianDetector()

    def test_og01_detects_error_rate_spike(self, detector):
        """OG-01: Error rate >5% triggers."""
        signals = {"error_pct": 8.5, "errors_by_segment": [{"error_pct": 8.5}]}
        matched = detector.run(signals)
        assert any(p.id == "OG-01" for p in matched)

    def test_og01_no_false_positive(self, detector):
        """OG-01: Error rate <=5% should NOT trigger."""
        signals = {"error_pct": 2.0, "errors_by_segment": [{"error_pct": 2.0}]}
        matched = detector.run(signals)
        assert not any(p.id == "OG-01" for p in matched)

    def test_og02_detects_support_outpacing_growth(self, detector):
        """OG-02: Support tickets growth >2x user growth."""
        signals = {"support_tickets_growth_pct": 40, "user_growth_pct": 10}
        matched = detector.run(signals)
        assert any(p.id == "OG-02" for p in matched)

    def test_og02_no_false_positive(self, detector):
        """OG-02: Support growth <=2x user growth should NOT trigger."""
        signals = {"support_tickets_growth_pct": 15, "user_growth_pct": 10}
        matched = detector.run(signals)
        assert not any(p.id == "OG-02" for p in matched)

    def test_og03_detects_cross_channel_bugs(self, detector):
        """OG-03: Bug reported in 3+ channels."""
        signals = {"bug_mentions_by_channel": {"twitter": 5, "intercom": 3, "email": 2}}
        matched = detector.run(signals)
        assert any(p.id == "OG-03" for p in matched)

    def test_og03_no_false_positive(self, detector):
        """OG-03: Bug in <3 channels should NOT trigger."""
        signals = {"bug_mentions_by_channel": {"twitter": 2, "intercom": 1}}
        matched = detector.run(signals)
        assert not any(p.id == "OG-03" for p in matched)

    def test_og04_detects_deploy_collapse(self, detector):
        """OG-04: Deploys this month <50% of last month."""
        signals = {"deploys_this_month": 2, "deploys_last_month": 8}
        matched = detector.run(signals)
        assert any(p.id == "OG-04" for p in matched)

    def test_og04_no_false_positive(self, detector):
        """OG-04: Deploys >=50% of last month should NOT trigger."""
        signals = {"deploys_this_month": 7, "deploys_last_month": 8}
        matched = detector.run(signals)
        assert not any(p.id == "OG-04" for p in matched)

    def test_og04_edge_case_zero_last_month(self, detector):
        """OG-04: Zero last month should NOT false positive."""
        signals = {"deploys_this_month": 5, "deploys_last_month": 0}
        matched = detector.run(signals)
        assert not any(p.id == "OG-04" for p in matched)

    def test_og05_detects_infra_cost_divergence(self, detector):
        """OG-05: Infra cost growth >2x user growth."""
        signals = {"aws_cost_growth_pct": 50, "user_growth_pct": 15}
        matched = detector.run(signals)
        assert any(p.id == "OG-05" for p in matched)

    def test_og05_no_false_positive(self, detector):
        """OG-05: Infra cost growth <=2x user growth should NOT trigger."""
        signals = {"aws_cost_growth_pct": 20, "user_growth_pct": 15}
        matched = detector.run(signals)
        assert not any(p.id == "OG-05" for p in matched)


class TestDomainFiltering:
    """Domain filtering tests."""

    @pytest.fixture
    def detector(self):
        return GuardianDetector()

    def test_run_by_domain_filters(self, detector):
        """run_by_domain returns only matching domain."""
        signals = {"monthly_churn_pct": 0.04, "error_pct": 8.5}
        finance_matches = detector.run_by_domain(signals, "finance")
        ops_matches = detector.run_by_domain(signals, "ops")

        assert all(p.domain == "finance" for p in finance_matches)
        assert all(p.domain == "ops" for p in ops_matches)

    def test_run_by_domain_empty_on_no_match(self, detector):
        """run_by_domain returns empty list when no patterns match."""
        signals = {"monthly_churn_pct": 0.01, "error_pct": 1.0}
        matched = detector.run_by_domain(signals, "finance")
        assert matched == []


class TestEdgeCases:
    """Edge case handling."""

    @pytest.fixture
    def detector(self):
        return GuardianDetector()

    def test_empty_signals_returns_empty(self, detector):
        """Empty signals should return empty matches."""
        matched = detector.run({})
        assert matched == []

    def test_missing_optional_signals_no_crash(self, detector):
        """Missing optional signals should not crash."""
        signals = {"monthly_churn_pct": 0.04}
        matched = detector.run(signals)
        assert isinstance(matched, list)

    def test_all_healthy_signals_returns_empty(self, detector):
        """All healthy signals should return no matches."""
        signals = {
            "monthly_churn_pct": 0.01,
            "net_burn": 5000,
            "net_new_arr": 10000,
            "top_customer_mrr": 1000,
            "total_mrr": 20000,
            "runway_months": 12,
            "new_signups": 100,
            "activation_rate": 60,
            "error_pct": 1.0,
        }
        matched = detector.run(signals)
        assert matched == []


class TestAllPatternsExist:
    """Verify all 17 patterns are registered."""

    def test_seventeen_patterns_registered(self):
        """All 17 patterns should be in SEED_STAGE_WATCHLIST."""
        from src.guardian.watchlist import SEED_STAGE_WATCHLIST

        assert len(SEED_STAGE_WATCHLIST) == 17

        ids = [p.id for p in SEED_STAGE_WATCHLIST]
        expected = [
            "FG-01", "FG-02", "FG-03", "FG-04", "FG-05", "FG-06",
            "BG-01", "BG-02", "BG-03", "BG-04", "BG-05", "BG-06",
            "OG-01", "OG-02", "OG-03", "OG-04", "OG-05",
        ]
        assert ids == expected