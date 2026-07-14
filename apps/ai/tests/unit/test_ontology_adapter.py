"""TDD tests for OntologyAI V4.2 — MissionState → Ontology Adapter (Task 2).

These tests are written FIRST and must FAIL (ImportError / not found)
until ``apps/ai/src/ontology/adapter.py`` is implemented.

Run:
    cd /home/aparna/Desktop/iterate_swarm/apps/ai
    uv run pytest tests/unit/test_ontology_adapter.py -v
"""
from datetime import datetime

from src.ontology.object_types import (
    OBJECT_TYPES,
    Customer,
    Deal,
    RevenueMetric,
    Incident,
    Message,
    PlannedAction,
)
from src.ontology.adapter import mission_state_to_ontology


# ---------------------------------------------------------------------------
# Empty / degenerate input
# ---------------------------------------------------------------------------
class TestEmptyState:
    """An empty MissionState must not raise and must yield an empty result."""

    def test_empty_dict_returns_empty_or_all_empty(self):
        result = mission_state_to_ontology({})
        assert isinstance(result, dict)
        # Either {} or a dict with all six object types mapped to empty lists.
        assert result == {} or (
            set(result.keys()) == set(OBJECT_TYPES)
            and all(len(v) == 0 for v in result.values())
        )

    def test_none_values_do_not_raise(self):
        state = {
            "mrr": None,
            "burn_rate": None,
            "runway_days": None,
            "customers": None,
            "deals": None,
        }
        result = mission_state_to_ontology(state)
        assert isinstance(result, dict)
        # No typed objects should be produced from None values.
        assert all(len(v) == 0 for v in result.values())


# ---------------------------------------------------------------------------
# Populated state maps into typed lists
# ---------------------------------------------------------------------------
class TestPopulatedState:
    """A populated MissionState maps known fields into typed Object lists."""

    def _sample_state(self) -> dict:
        # Mix of real flat MissionState keys (mrr, burn_rate, runway_days,
        # burn_severity, mrr_trend, churn_rate, active_alerts, error_spike,
        # founder_focus, trust_score, ...) plus the object-type list keys the
        # adapter recognizes (customers, deals, incidents, ...).
        return {
            # --- real flat MissionState scalar keys ---
            "tenant_id": "tenant_acme",
            "mrr": 50000.0,
            "burn_rate": 40000.0,
            "runway_days": 12,
            "burn_severity": "high",
            "mrr_trend": "declining",
            "churn_rate": 0.05,
            "active_alerts": "inc-1,inc-2",
            "error_spike": True,
            "founder_focus": "retention",
            "trust_score": 0.8,
            # --- object-type list keys (recognized by the adapter) ---
            "customers": [
                {
                    "id": "cust-1",
                    "name": "Acme Corp",
                    "mrr": 1000.0,
                    "health_score": 0.9,
                    "last_contact_at": datetime(2026, 7, 1, 12, 0, 0),
                },
                {
                    "id": "cust-2",
                    "name": "Globex",
                    "mrr": 2500.0,
                    "health_score": 0.4,
                    "last_contact_at": None,
                },
            ],
            "deals": [
                {
                    "id": "deal-1",
                    "stage": "negotiation",
                    "value": 25000.0,
                    "close_probability": 0.6,
                    "owner": "alice",
                },
            ],
            "incidents": [
                {
                    "id": "inc-1",
                    "severity": "high",
                    "opened_at": datetime(2026, 7, 10, 9, 0, 0),
                    "resolved_at": None,
                    "root_cause": "db failover",
                },
            ],
        }

    def test_all_six_object_types_present_as_keys(self):
        result = mission_state_to_ontology(self._sample_state())
        assert set(result.keys()) == set(OBJECT_TYPES)
        for name in OBJECT_TYPES:
            assert isinstance(result[name], list)

    def test_customers_mapped_to_typed_list(self):
        result = mission_state_to_ontology(self._sample_state())
        assert len(result["Customer"]) == 2
        assert all(isinstance(c, Customer) for c in result["Customer"])
        assert result["Customer"][0].name == "Acme Corp"
        assert result["Customer"][1].health_score == 0.4

    def test_deals_mapped_to_typed_list(self):
        result = mission_state_to_ontology(self._sample_state())
        assert len(result["Deal"]) == 1
        assert isinstance(result["Deal"][0], Deal)
        assert result["Deal"][0].value == 25000.0
        assert result["Deal"][0].owner == "alice"

    def test_incidents_mapped_to_typed_list(self):
        result = mission_state_to_ontology(self._sample_state())
        assert len(result["Incident"]) == 1
        assert isinstance(result["Incident"][0], Incident)
        assert result["Incident"][0].severity == "high"
        assert result["Incident"][0].root_cause == "db failover"

    def test_revenue_metric_derived_from_flat_scalars(self):
        # The flat MissionState carries mrr/burn_rate/runway_days but no
        # explicit revenue_metrics list — the adapter derives one.
        result = mission_state_to_ontology(self._sample_state())
        assert len(result["RevenueMetric"]) == 1
        rm = result["RevenueMetric"][0]
        assert isinstance(rm, RevenueMetric)
        assert rm.mrr == 50000.0
        assert rm.burn == 40000.0
        assert rm.runway_days == 12
        assert isinstance(rm.runway_days, int)

    def test_absent_types_yield_empty_lists(self):
        result = mission_state_to_ontology(self._sample_state())
        # No messages / planned_actions in the sample state.
        assert result["Message"] == []
        assert result["PlannedAction"] == []


# ---------------------------------------------------------------------------
# Tolerant: unknown / legacy keys are ignored without raising
# ---------------------------------------------------------------------------
class TestUnknownKeysIgnored:
    """Legacy or unknown keys must be ignored, never raise."""

    def test_unknown_legacy_keys_ignored(self):
        state = {
            "legacy_customer_blob": {"foo": "bar"},
            "old_v1_deals": [{"x": 1}],
            "random_metric": 123,
            "deprecated_flag": True,
            "mrr": 1000.0,  # recognized scalar -> RevenueMetric derived
        }
        result = mission_state_to_ontology(state)
        assert isinstance(result, dict)
        # Unknown keys must not leak into the output object-type keys.
        assert "legacy_customer_blob" not in result
        assert "old_v1_deals" not in result
        # Recognized scalar still produces a derived RevenueMetric.
        assert len(result["RevenueMetric"]) == 1

    def test_only_unknown_keys_yields_empty_lists(self):
        state = {
            "foo": "bar",
            "baz": [1, 2, 3],
            "nested": {"a": "b"},
        }
        result = mission_state_to_ontology(state)
        assert isinstance(result, dict)
        assert all(len(v) == 0 for v in result.values())

    def test_malformed_list_items_skipped_not_raised(self):
        # A recognized list key whose items fail strict validation must be
        # skipped (tolerant), not raise.
        state = {
            "customers": [
                {"id": "c1", "name": "Good", "mrr": 10.0, "health_score": 0.5},
                {"id": "c2", "name": "Bad", "mrr": "not-a-float"},  # invalid
                {"not": "a customer at all"},  # missing required fields
            ],
        }
        result = mission_state_to_ontology(state)
        # Only the single valid item survives; no exception raised.
        assert len(result["Customer"]) == 1
        assert result["Customer"][0].id == "c1"


# ---------------------------------------------------------------------------
# Accepts a MissionState dataclass / pydantic model too (not just dict)
# ---------------------------------------------------------------------------
class TestNonDictInput:
    """The adapter should tolerate being handed a MissionState object."""

    def test_dataclass_mission_state_accepted(self):
        from dataclasses import dataclass

        @dataclass
        class MiniMissionState:
            tenant_id: str
            mrr: float = 0.0
            burn_rate: float = 0.0
            runway_days: int = 0

        state = MiniMissionState(tenant_id="t", mrr=9000.0, burn_rate=3000.0, runway_days=30)
        result = mission_state_to_ontology(state)
        assert isinstance(result, dict)
        assert len(result["RevenueMetric"]) == 1
        assert result["RevenueMetric"][0].mrr == 9000.0
