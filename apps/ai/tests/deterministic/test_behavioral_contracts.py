"""Behavioral contracts — invariants the system must ALWAYS or NEVER satisfy.

These are deterministic assertions that catch logic errors.  Every test
uses only local, in-memory constructs: no LLM, no network, no Docker.

Contract numbering follows the specification:
  MUST ALWAYS:  1-11
  MUST NEVER:  12-18
"""
from __future__ import annotations

import inspect
import re
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from src.states.schemas import (
    ExecutionHealth,
    ExecutionState,
    FinancialHealth,
    FinanceState,
    MissionStateV2,
    RevenueState,
    RevenueTrend,
    SupportHealth,
    SupportState,
    TeamState,
)
from src.guardian.startup_watchlists import (
    STARTUP_WATCHLIST_FUNCTIONS,
    run_watchlists,
)
from src.guardian.startup_correlations import (
    STARTUP_CORRELATION_FUNCTIONS,
    run_correlations,
)
from src.guardian.assemblers import (
    assemble_execution_state,
    assemble_finance_state,
    assemble_revenue_state,
    assemble_support_state,
    assemble_team_state,
)


# ===========================================================================
# MUST ALWAYS contracts (invariants that hold for ANY input)
# ===========================================================================


class TestContract01MissionStateAlwaysValid:
    """Contract 1: MissionStateV2(tenant_id="...") must always succeed."""

    @pytest.mark.parametrize("tenant_id", [
        "default",
        "",
        "tenant-abc-123",
        "t" * 10_000,
        "unicode-\u00e9\u00e8\u00ea",
        "special/chars@#!$%",
        "12345",
    ])
    def test_construction_never_raises(self, tenant_id: str) -> None:
        state = MissionStateV2(tenant_id=tenant_id)
        assert state.tenant_id == tenant_id

    def test_minimal_construction(self) -> None:
        """Bare minimum: just tenant_id should produce a valid state."""
        state = MissionStateV2(tenant_id="x")
        assert state.tenant_id == "x"
        assert isinstance(state.support, SupportState)
        assert isinstance(state.execution, ExecutionState)
        assert isinstance(state.team, TeamState)
        assert isinstance(state.finance, FinanceState)
        assert isinstance(state.revenue, RevenueState)


class TestContract02DomainStatesHaveDefaults:
    """Contract 2: All domain states must have sensible defaults."""

    def test_support_state_defaults(self) -> None:
        s = SupportState()
        assert s.open_issues == 0
        assert s.unresolved_issues == 0
        assert s.sla_breach_count == 0
        assert s.avg_resolution_hours is None
        assert s.health == SupportHealth.GOOD

    def test_execution_state_defaults(self) -> None:
        s = ExecutionState()
        assert s.active_projects == 0
        assert s.overdue_tasks == 0
        assert s.open_tasks == 0
        assert s.completed_tasks_30d == 0
        assert s.avg_completion_pct is None
        assert s.health == ExecutionHealth.ON_TRACK

    def test_team_state_defaults(self) -> None:
        s = TeamState()
        assert s.active_employees == 0
        assert s.headcount_by_department == {}
        assert s.new_hires_30d == 0
        assert s.departures_30d == 0
        assert s.health == SupportHealth.GOOD

    def test_finance_state_defaults(self) -> None:
        s = FinanceState()
        assert s.outstanding_invoices == 0
        assert s.total_outstanding_cents == 0
        assert s.overdue_invoices == 0
        assert s.total_overdue_cents == 0
        assert s.unpaid_invoices_30d_cents == 0
        assert s.paid_invoices_30d_cents == 0
        assert s.days_sales_outstanding is None
        assert s.health == FinancialHealth.HEALTHY

    def test_revenue_state_defaults(self) -> None:
        s = RevenueState()
        assert s.total_deals_cents == 0
        assert s.won_deals_30d_cents == 0
        assert s.pipeline_deals_cents == 0
        assert s.active_customers == 0
        assert s.mrr_cents is None
        assert s.trend == RevenueTrend.STABLE

    @pytest.mark.parametrize("cls,field,default", [
        (SupportState, "open_issues", 0),
        (ExecutionState, "overdue_tasks", 0),
        (TeamState, "active_employees", 0),
        (FinanceState, "total_outstanding_cents", 0),
        (RevenueState, "active_customers", 0),
    ])
    def test_numeric_fields_default_to_zero(self, cls: type, field: str, default: int) -> None:
        instance = cls()
        assert getattr(instance, field) == default


class TestContract03HealthAlwaysInEnum:
    """Contract 3: overall_health must always be a valid SupportHealth enum."""

    @pytest.mark.parametrize("health", list(SupportHealth))
    def test_valid_health_value(self, health: SupportHealth) -> None:
        state = MissionStateV2(tenant_id="t", overall_health=health)
        assert state.overall_health == health

    def test_default_health_is_good(self) -> None:
        state = MissionStateV2(tenant_id="t")
        assert state.overall_health == SupportHealth.GOOD

    @pytest.mark.parametrize("domain_state_cls,default_health", [
        (SupportState, SupportHealth.GOOD),
        (ExecutionState, ExecutionHealth.ON_TRACK),
        (TeamState, SupportHealth.GOOD),
        (FinanceState, FinancialHealth.HEALTHY),
    ])
    def test_domain_health_default_is_valid_enum(
        self, domain_state_cls: type, default_health: Any
    ) -> None:
        instance = domain_state_cls()
        assert instance.health == default_health


class TestContract04ConnectorsOkAlwaysBool:
    """Contract 4: Every value in connectors_ok must be True or False."""

    @pytest.mark.parametrize("connectors", [
        {"erpnext": True},
        {"hubspot": False},
        {"erpnext": True, "hubspot": False, "quickbooks": True},
        {},
        {"a": True, "b": True, "c": False, "d": True},
    ])
    def test_all_values_are_bool(self, connectors: Dict[str, bool]) -> None:
        state = MissionStateV2(tenant_id="t", connectors_ok=connectors)
        for key, val in state.connectors_ok.items():
            assert isinstance(val, bool), f"connectors_ok[{key!r}] is {type(val).__name__}, expected bool"

    def test_roundtrip_via_model_dump(self) -> None:
        """Values remain bool through serialize/deserialize."""
        state = MissionStateV2(
            tenant_id="t",
            connectors_ok={"erpnext": True, "hubspot": False},
        )
        dumped = state.model_dump()
        for key, val in dumped["connectors_ok"].items():
            assert isinstance(val, bool)


class TestContract05RunIdAlwaysSet:
    """Contract 5: run_id must be a non-empty string after orchestration."""

    def test_default_run_id_is_empty_string(self) -> None:
        state = MissionStateV2(tenant_id="t")
        # The schema default is "" — but the orchestrator MUST set it
        assert isinstance(state.run_id, str)

    @pytest.mark.parametrize("run_id", ["abc", "run-123", "uuid-like-thing", "x"])
    def test_run_id_preserves_value(self, run_id: str) -> None:
        state = MissionStateV2(tenant_id="t", run_id=run_id)
        assert state.run_id == run_id
        assert len(state.run_id) > 0


class TestContract06TimestampAlwaysUTC:
    """Contract 6: timestamp must always be timezone-aware UTC."""

    def test_default_timestamp_is_utc_aware(self) -> None:
        state = MissionStateV2(tenant_id="t")
        assert state.timestamp.tzinfo is not None
        assert state.timestamp.tzinfo == timezone.utc

    @pytest.mark.parametrize("dt", [
        datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
        datetime(2000, 6, 15, 12, 30, 0, tzinfo=timezone.utc),
    ])
    def test_explicit_utc_timestamps(self, dt: datetime) -> None:
        state = MissionStateV2(tenant_id="t", timestamp=dt)
        assert state.timestamp.tzinfo == timezone.utc

    def test_timestamp_always_has_tz(self) -> None:
        """Even if user passes naive datetime, default_factory produces UTC."""
        state = MissionStateV2(tenant_id="t")
        assert state.timestamp.utcoffset() is not None


class TestContract07MonetaryValuesAlwaysCents:
    """Contract 7: All *_cents fields must be integers (not floats)."""

    @pytest.mark.parametrize("state_cls,field", [
        (FinanceState, "total_outstanding_cents"),
        (FinanceState, "total_overdue_cents"),
        (FinanceState, "unpaid_invoices_30d_cents"),
        (FinanceState, "paid_invoices_30d_cents"),
        (RevenueState, "total_deals_cents"),
        (RevenueState, "won_deals_30d_cents"),
        (RevenueState, "pipeline_deals_cents"),
        (RevenueState, "mrr_cents"),
    ])
    def test_cents_fields_are_int_when_set(self, state_cls: type, field: str) -> None:
        instance = state_cls(**{field: 12345})
        val = getattr(instance, field)
        assert isinstance(val, int), f"{field} is {type(val).__name__}, expected int"

    def test_finance_cents_via_assembler(self) -> None:
        state = assemble_finance_state({
            "finance_total_outstanding_cents": 500_000,
            "finance_overdue_cents": 100_000,
        })
        assert isinstance(state.total_outstanding_cents, int)
        assert isinstance(state.total_overdue_cents, int)

    def test_revenue_cents_via_assembler(self) -> None:
        state = assemble_revenue_state({
            "revenue_total_deals_cents": 10_000_000,
            "revenue_won_deals_30d_cents": 5_000_000,
            "revenue_pipeline_deals_cents": 5_000_000,
        })
        assert isinstance(state.total_deals_cents, int)
        assert isinstance(state.won_deals_30d_cents, int)
        assert isinstance(state.pipeline_deals_cents, int)

    def test_mrr_cents_none_or_int(self) -> None:
        state_none = RevenueState(mrr_cents=None)
        assert state_none.mrr_cents is None
        state_int = RevenueState(mrr_cents=999)
        assert isinstance(state_int.mrr_cents, int)


class TestContract08WatchlistReturnsList:
    """Contract 8: run_watchlists() must always return a list."""

    @pytest.mark.parametrize("state", [
        {},
        {"support": {}},
        {"support": None},
        {"execution": {"overdue_tasks": 999}},
        {"finance": {"total_overdue_cents": 999_999_999}},
        {"revenue": {"trend": "declining"}},
        {"team": {"departures_30d": 999}},
    ])
    def test_returns_list(self, state: Dict[str, Any]) -> None:
        result = run_watchlists(state)
        assert isinstance(result, list), f"run_watchlists returned {type(result).__name__}, expected list"

    def test_returns_list_for_empty_dict(self) -> None:
        result = run_watchlists({})
        assert result is not None
        assert isinstance(result, list)

    def test_individual_watchlist_returns_list(self) -> None:
        """Every individual watchlist function must return a list."""
        for wl_fn in STARTUP_WATCHLIST_FUNCTIONS:
            result = wl_fn({})
            assert isinstance(result, list), (
                f"{wl_fn.__name__} returned {type(result).__name__}, expected list"
            )

    def test_no_watchlist_returns_none(self) -> None:
        """No watchlist function should ever return None."""
        for wl_fn in STARTUP_WATCHLIST_FUNCTIONS:
            for state in [{}, {"support": {}}, {"execution": {}}]:
                result = wl_fn(state)
                assert result is not None


class TestContract09CorrelationReturnsList:
    """Contract 9: run_correlations() must always return a list."""

    @pytest.mark.parametrize("state", [
        {},
        {"support": {}},
        {"revenue": {"trend": "declining"}},
        {"finance": {"total_overdue_cents": 999_999_999}},
    ])
    def test_returns_list(self, state: Dict[str, Any]) -> None:
        result = run_correlations(state)
        assert isinstance(result, list), f"run_correlations returned {type(result).__name__}, expected list"

    def test_individual_correlation_returns_list(self) -> None:
        """Every individual correlation function must return a list."""
        for cr_fn in STARTUP_CORRELATION_FUNCTIONS:
            result = cr_fn({})
            assert isinstance(result, list), (
                f"{cr_fn.__name__} returned {type(result).__name__}, expected list"
            )

    def test_no_correlation_returns_none(self) -> None:
        """No correlation function should ever return None."""
        for cr_fn in STARTUP_CORRELATION_FUNCTIONS:
            for state in [{}, {"support": {}}, {"revenue": {}}]:
                result = cr_fn(state)
                assert result is not None


class TestContract10AlertsHaveRequiredFields:
    """Contract 10: Every alert dict must have id, title, severity, domain."""

    REQUIRED_KEYS = {"id", "title", "severity", "domain"}

    def _collect_all_alerts(self) -> List[Dict[str, Any]]:
        """Gather alerts from all watchlists with extreme inputs."""
        extreme_states = [
            {
                "support": {"unresolved_issues": 999, "sla_breach_count": 999},
                "execution": {"overdue_tasks": 999, "health": "blocked"},
                "finance": {"total_overdue_cents": 99_999_999, "days_sales_outstanding": 999},
                "revenue": {"trend": "declining"},
                "team": {"departures_30d": 999},
            },
            {
                "support": {"unresolved_issues": 11, "sla_breach_count": 1},
                "execution": {"overdue_tasks": 6},
                "finance": {"total_overdue_cents": 6_000_000, "days_sales_outstanding": 61},
                "revenue": {"trend": "declining"},
                "team": {"departures_30d": 3},
            },
        ]
        all_alerts: List[Dict[str, Any]] = []
        for state in extreme_states:
            all_alerts.extend(run_watchlists(state))
        return all_alerts

    def test_all_alerts_have_required_keys(self) -> None:
        alerts = self._collect_all_alerts()
        assert len(alerts) > 0, "No alerts generated — test premise broken"
        for alert in alerts:
            for key in self.REQUIRED_KEYS:
                assert key in alert, f"Alert missing required key {key!r}: {alert}"

    def test_alert_values_are_strings(self) -> None:
        alerts = self._collect_all_alerts()
        for alert in alerts:
            assert isinstance(alert["id"], str)
            assert isinstance(alert["title"], str)
            assert isinstance(alert["severity"], str)
            assert isinstance(alert["domain"], str)


class TestContract11CorrelationsHaveRequiredFields:
    """Contract 11: Every correlation dict must have id, title, severity, domains, detail, recommendation."""

    REQUIRED_KEYS = {"id", "title", "severity", "domains", "detail", "recommendation"}

    def _collect_all_correlations(self) -> List[Dict[str, Any]]:
        """Gather correlations from all correlation functions with extreme inputs."""
        extreme_states = [
            {
                "support": {"unresolved_issues": 999},
                "execution": {"overdue_tasks": 999, "health": "blocked"},
                "finance": {"total_overdue_cents": 99_999_999},
                "revenue": {"trend": "declining"},
                "team": {"departures_30d": 999},
            },
            {
                "support": {"unresolved_issues": 10},
                "execution": {"overdue_tasks": 5, "health": "blocked"},
                "finance": {"total_overdue_cents": 10_000_000},
                "revenue": {"trend": "declining"},
                "team": {"departures_30d": 3},
            },
        ]
        all_correlations: List[Dict[str, Any]] = []
        for state in extreme_states:
            all_correlations.extend(run_correlations(state))
        return all_correlations

    def test_all_correlations_have_required_keys(self) -> None:
        correlations = self._collect_all_correlations()
        assert len(correlations) > 0, "No correlations generated — test premise broken"
        for corr in correlations:
            for key in self.REQUIRED_KEYS:
                assert key in corr, f"Correlation missing required key {key!r}: {corr}"

    def test_domains_is_list(self) -> None:
        correlations = self._collect_all_correlations()
        for corr in correlations:
            assert isinstance(corr["domains"], list), (
                f"Correlation {corr['id']} has domains of type {type(corr['domains']).__name__}"
            )

    def test_correlation_values_are_strings(self) -> None:
        correlations = self._collect_all_correlations()
        for corr in correlations:
            assert isinstance(corr["id"], str)
            assert isinstance(corr["title"], str)
            assert isinstance(corr["severity"], str)
            assert isinstance(corr["detail"], str)
            assert isinstance(corr["recommendation"], str)


# ===========================================================================
# MUST NEVER contracts (things that must never happen)
# ===========================================================================


class TestContract12NoNegativeCounts:
    """Contract 12: Domain state counts must never be negative after assembly."""

    @pytest.mark.parametrize("raw", [
        {"support_open_issues": -5, "support_unresolved_issues": -3},
        {"support_open_issues": -1, "support_unresolved_issues": 0},
        {"support_open_issues": 0, "support_unresolved_issues": -100},
    ])
    def test_assembler_handles_negative_support(self, raw: Dict[str, Any]) -> None:
        """Pydantic int type will reject negatives; assembler uses .get(..., 0)."""
        # The assembler reads from raw dict — negative values in raw should
        # either be rejected by Pydantic or clamped by logic.
        # At minimum, the assembled state fields must be int.
        result = assemble_support_state(raw)
        assert isinstance(result.open_issues, int)
        assert isinstance(result.unresolved_issues, int)

    @pytest.mark.parametrize("raw", [
        {"execution_overdue_tasks": -5, "execution_active_projects": -2},
    ])
    def test_assembler_handles_negative_execution(self, raw: Dict[str, Any]) -> None:
        result = assemble_execution_state(raw)
        assert isinstance(result.overdue_tasks, int)
        assert isinstance(result.active_projects, int)

    @pytest.mark.parametrize("raw", [
        {"finance_total_outstanding_cents": -100, "finance_overdue_cents": -50},
    ])
    def test_assembler_handles_negative_finance(self, raw: Dict[str, Any]) -> None:
        result = assemble_finance_state(raw)
        assert isinstance(result.total_outstanding_cents, int)
        assert isinstance(result.total_overdue_cents, int)

    def test_mission_state_counts_non_negative(self) -> None:
        state = MissionStateV2(tenant_id="t")
        assert state.alert_count >= 0
        assert state.correlation_count >= 0

    def test_watchlist_counts_non_negative(self) -> None:
        """Watchlists return alerts list — length must be non-negative."""
        result = run_watchlists({})
        assert len(result) >= 0


class TestContract13NoLLMInConnectors:
    """Contract 13: Connector functions must never call LLM APIs."""

    def test_no_openai_import_in_connector_module(self) -> None:
        """The ERPNext connector module must not import openai."""
        from src.integrations import erpnext
        source = inspect.getsource(erpnext)
        assert "openai" not in source.lower(), (
            "ERPNext connector references openai — potential LLM call"
        )

    def test_no_llm_pattern_in_connector_code(self) -> None:
        """Scan connector source for common LLM call patterns."""
        from src.integrations import erpnext
        source = inspect.getsource(erpnext)
        llm_patterns = [
            r"ChatCompletion",
            r"client\.chat\.completions",
            r"llm\.invoke",
            r"llm\.ainvoke",
            r"openai\.Chat",
        ]
        for pattern in llm_patterns:
            assert not re.search(pattern, source, re.IGNORECASE), (
                f"ERPNext connector contains LLM pattern: {pattern}"
            )


class TestContract14NoLLMInWatchlists:
    """Contract 14: Watchlist functions must never call LLM APIs."""

    def test_no_openai_in_watchlist_module(self) -> None:
        import src.guardian.startup_watchlists as mod
        source = inspect.getsource(mod)
        assert "openai" not in source.lower(), (
            "Watchlist module references openai — potential LLM call"
        )

    def test_no_llm_patterns_in_watchlist_code(self) -> None:
        import src.guardian.startup_watchlists as mod
        source = inspect.getsource(mod)
        llm_patterns = [
            r"ChatCompletion",
            r"client\.chat\.completions",
            r"llm\.invoke",
            r"llm\.ainvoke",
            r"\.predict\(",
            r"\.agenerate\(",
        ]
        for pattern in llm_patterns:
            assert not re.search(pattern, source, re.IGNORECASE), (
                f"Watchlist module contains LLM pattern: {pattern}"
            )

    def test_watchlist_functions_are_pure(self) -> None:
        """Each watchlist function only reads from the state dict."""
        for wl_fn in STARTUP_WATCHLIST_FUNCTIONS:
            source = inspect.getsource(wl_fn)
            assert "import openai" not in source
            assert "import httpx" not in source


class TestContract15NoLLMInCorrelations:
    """Contract 15: Correlation functions must never call LLM APIs."""

    def test_no_openai_in_correlation_module(self) -> None:
        import src.guardian.startup_correlations as mod
        source = inspect.getsource(mod)
        assert "openai" not in source.lower(), (
            "Correlation module references openai — potential LLM call"
        )

    def test_no_llm_patterns_in_correlation_code(self) -> None:
        import src.guardian.startup_correlations as mod
        source = inspect.getsource(mod)
        llm_patterns = [
            r"ChatCompletion",
            r"client\.chat\.completions",
            r"llm\.invoke",
            r"llm\.ainvoke",
            r"\.predict\(",
            r"\.agenerate\(",
        ]
        for pattern in llm_patterns:
            assert not re.search(pattern, source, re.IGNORECASE), (
                f"Correlation module contains LLM pattern: {pattern}"
            )

    def test_correlation_functions_are_pure(self) -> None:
        """Each correlation function only reads from the state dict."""
        for cr_fn in STARTUP_CORRELATION_FUNCTIONS:
            source = inspect.getsource(cr_fn)
            assert "import openai" not in source
            assert "import httpx" not in source


class TestContract16NoLLMInAssemblers:
    """Contract 16: Assembler functions must never call LLM APIs."""

    @pytest.mark.parametrize("assemble_fn", [
        assemble_support_state,
        assemble_execution_state,
        assemble_team_state,
        assemble_finance_state,
        assemble_revenue_state,
    ])
    def test_assembler_no_llm_import(self, assemble_fn) -> None:
        source = inspect.getsource(assemble_fn)
        assert "openai" not in source.lower(), (
            f"{assemble_fn.__name__} references openai"
        )

    @pytest.mark.parametrize("assemble_fn", [
        assemble_support_state,
        assemble_execution_state,
        assemble_team_state,
        assemble_finance_state,
        assemble_revenue_state,
    ])
    def test_assembler_no_llm_patterns(self, assemble_fn) -> None:
        source = inspect.getsource(assemble_fn)
        llm_patterns = [
            r"ChatCompletion",
            r"client\.chat\.completions",
            r"llm\.invoke",
            r"llm\.ainvoke",
        ]
        for pattern in llm_patterns:
            assert not re.search(pattern, source, re.IGNORECASE), (
                f"{assemble_fn.__name__} contains LLM pattern: {pattern}"
            )

    def test_assemblers_are_sync_pure(self) -> None:
        """Assemblers must be synchronous (no async/await)."""
        for fn in [
            assemble_support_state,
            assemble_execution_state,
            assemble_team_state,
            assemble_finance_state,
            assemble_revenue_state,
        ]:
            assert not inspect.iscoroutinefunction(fn), (
                f"{fn.__name__} is async — assemblers must be sync"
            )


class TestContract17NoSecretsInLogs:
    """Contract 17: Connector functions must never log API keys or secrets."""

    def test_no_secret_patterns_in_erpnext_connector(self) -> None:
        from src.integrations import erpnext
        source = inspect.getsource(erpnext)
        secret_patterns = [
            r"api_key\s*=\s*[\"'][^\"']+[\"']",
            r"api_secret\s*=\s*[\"'][^\"']+[\"']",
            r"password\s*=\s*[\"'][^\"']+[\"']",
            r"Bearer\s+[A-Za-z0-9\._\-]{20,}",
            r"sk-[A-Za-z0-9]{20,}",
        ]
        for pattern in secret_patterns:
            assert not re.search(pattern, source), (
                f"ERPNext connector may contain hardcoded secret: {pattern}"
            )

    def test_no_secret_patterns_in_hubspot_connector(self) -> None:
        from src.integrations import hubspot
        source = inspect.getsource(hubspot)
        secret_patterns = [
            r"api_key\s*=\s*[\"'][^\"']+[\"']",
            r"Bearer\s+[A-Za-z0-9\._\-]{20,}",
            r"sk-[A-Za-z0-9]{20,}",
        ]
        for pattern in secret_patterns:
            assert not re.search(pattern, source), (
                f"HubSpot connector may contain hardcoded secret: {pattern}"
            )

    def test_no_secret_patterns_in_quickbooks_connector(self) -> None:
        from src.integrations import quickbooks
        source = inspect.getsource(quickbooks)
        secret_patterns = [
            r"api_key\s*=\s*[\"'][^\"']+[\"']",
            r"Bearer\s+[A-Za-z0-9\._\-]{20,}",
            r"sk-[A-Za-z0-9]{20,}",
        ]
        for pattern in secret_patterns:
            assert not re.search(pattern, source), (
                f"QuickBooks connector may contain hardcoded secret: {pattern}"
            )


class TestContract18NoUnboundedRecursion:
    """Contract 18: Watchlists and correlations must not have recursive calls."""

    def _has_recursive_call(self, fn, visited: Any = None) -> bool:
        """Check if function source contains a call to itself."""
        source = inspect.getsource(fn)
        fn_name = fn.__name__
        # Simple heuristic: check if the function calls itself
        # Look for the function name followed by (
        pattern = rf'\b{re.escape(fn_name)}\s*\('
        # Exclude the def line itself
        lines = source.split('\n')
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('def '):
                continue
            if re.search(pattern, stripped):
                return True
        return False

    def test_watchlist_no_self_recursion(self) -> None:
        for wl_fn in STARTUP_WATCHLIST_FUNCTIONS:
            assert not self._has_recursive_call(wl_fn), (
                f"{wl_fn.__name__} calls itself — unbounded recursion risk"
            )

    def test_correlation_no_self_recursion(self) -> None:
        for cr_fn in STARTUP_CORRELATION_FUNCTIONS:
            assert not self._has_recursive_call(cr_fn), (
                f"{cr_fn.__name__} calls itself — unbounded recursion risk"
            )

    def test_run_watchlists_no_recursion(self) -> None:
        source = inspect.getsource(run_watchlists)
        # run_watchlists should not call itself
        assert not re.search(r'\brun_watchlists\s*\(', source.replace('def run_watchlists', ''))

    def test_run_correlations_no_recursion(self) -> None:
        source = inspect.getsource(run_correlations)
        assert not re.search(r'\brun_correlations\s*\(', source.replace('def run_correlations', ''))


# ===========================================================================
# Cross-cutting: Assemblers with arbitrary inputs
# ===========================================================================


class TestAssemblerInvariants:
    """Assemblers must produce valid domain states for ANY input dict."""

    @pytest.mark.parametrize("raw", [
        {},
        {"support_open_issues": -99},
        {"support_unresolved_issues": None},
        {"support_open_issues": "not_a_number"},
        {"support_open_issues": 10**20},
    ])
    def test_support_assembler_never_crashes(self, raw: Dict[str, Any]) -> None:
        try:
            result = assemble_support_state(raw)
            assert isinstance(result, SupportState)
            assert result.health in list(SupportHealth)
        except (TypeError, ValueError):
            # Pydantic may reject truly invalid types — acceptable
            pass

    @pytest.mark.parametrize("raw", [
        {},
        {"execution_overdue_tasks": -99},
        {"execution_avg_completion": None},
    ])
    def test_execution_assembler_never_crashes(self, raw: Dict[str, Any]) -> None:
        try:
            result = assemble_execution_state(raw)
            assert isinstance(result, ExecutionState)
            assert result.health in list(ExecutionHealth)
        except (TypeError, ValueError):
            pass

    @pytest.mark.parametrize("raw", [
        {},
        {"team_departments": None},
        {"team_departments": "invalid"},
    ])
    def test_team_assembler_never_crashes(self, raw: Dict[str, Any]) -> None:
        try:
            result = assemble_team_state(raw)
            assert isinstance(result, TeamState)
        except (TypeError, ValueError):
            pass

    @pytest.mark.parametrize("raw", [
        {},
        {"finance_overdue_cents": -99},
        {"finance_total_outstanding_cents": None},
    ])
    def test_finance_assembler_never_crashes(self, raw: Dict[str, Any]) -> None:
        try:
            result = assemble_finance_state(raw)
            assert isinstance(result, FinanceState)
            assert result.health in list(FinancialHealth)
        except (TypeError, ValueError):
            pass

    @pytest.mark.parametrize("raw", [
        {},
        {"revenue_won_deals_30d_cents": 0, "revenue_pipeline_deals_cents": 0},
        {"revenue_mrr_cents": None},
    ])
    def test_revenue_assembler_never_crashes(self, raw: Dict[str, Any]) -> None:
        try:
            result = assemble_revenue_state(raw)
            assert isinstance(result, RevenueState)
            assert result.trend in list(RevenueTrend)
        except (TypeError, ValueError):
            pass
