"""TDD tests for OntologyAI V5.1 — State → Ontology Adapter (PRD §12).

Run:
    cd /home/aparna/Desktop/iterate_swarm/apps/ai
    uv run pytest tests/unit/test_ontology_adapter.py -v
"""
from src.ontology.object_types import (
    OBJECT_TYPES,
    Party,
    Engagement,
    MoneyEvent,
    Issue,
    Message,
    PlannedAction,
)
from src.ontology.adapter import (
    mission_state_to_ontology,
    engagement_state_to_ontology,
)


class TestEmptyState:
    def test_empty_dict_returns_empty_or_all_empty(self):
        result = mission_state_to_ontology({})
        assert isinstance(result, dict)
        assert result == {} or (
            set(result.keys()) == set(OBJECT_TYPES)
            and all(len(v) == 0 for v in result.values())
        )

    def test_none_values_do_not_raise(self):
        state = {"mrr": None, "burn_rate": None, "parties": None}
        result = mission_state_to_ontology(state)
        assert isinstance(result, dict)
        assert all(len(v) == 0 for v in result.values())


class TestPopulatedLegacyState:
    def _sample_state(self) -> dict:
        return {
            "tenant_id": "tenant_acme",
            "mrr": 50000.0,
            "burn_rate": 40000.0,
            "parties": [
                {"id": "p-1", "kind": "customer", "name": "Acme Corp",
                 "status": "active", "owner": "alice",
                 "contact_points": ["email:a@x.com"], "notes": None,
                 "source_refs": ["s1"]},
            ],
            "engagements": [
                {"id": "e-1", "kind": "deal", "title": "Big Deal",
                 "status": "active", "owner": "bob", "value": 25000.0,
                 "due_date": None, "notes": None, "source_refs": []},
            ],
            "issues": [
                {"id": "i-1", "kind": "delay", "severity": "high",
                 "status": "open", "opened_at": None, "resolved_at": None,
                 "owner": None, "summary": "delayed", "notes": None,
                 "source_refs": []},
            ],
        }

    def test_all_six_object_types_present_as_keys(self):
        result = mission_state_to_ontology(self._sample_state())
        assert set(result.keys()) == set(OBJECT_TYPES)
        for name in OBJECT_TYPES:
            assert isinstance(result[name], list)

    def test_parties_mapped_to_typed_list(self):
        result = mission_state_to_ontology(self._sample_state())
        assert len(result["Party"]) == 1
        assert isinstance(result["Party"][0], Party)
        assert result["Party"][0].name == "Acme Corp"

    def test_engagements_mapped_to_typed_list(self):
        result = mission_state_to_ontology(self._sample_state())
        assert len(result["Engagement"]) == 1
        assert isinstance(result["Engagement"][0], Engagement)
        assert result["Engagement"][0].value == 25000.0

    def test_issues_mapped_to_typed_list(self):
        result = mission_state_to_ontology(self._sample_state())
        assert len(result["Issue"]) == 1
        assert isinstance(result["Issue"][0], Issue)
        assert result["Issue"][0].severity == "high"

    def test_money_events_derived_from_flat_scalars(self):
        result = mission_state_to_ontology(self._sample_state())
        # mrr -> receivable, burn_rate -> expense
        assert len(result["MoneyEvent"]) == 2
        kinds = {m.kind for m in result["MoneyEvent"]}
        assert "receivable" in kinds
        assert "expense" in kinds

    def test_absent_types_yield_empty_lists(self):
        result = mission_state_to_ontology(self._sample_state())
        assert result["Message"] == []
        assert result["PlannedAction"] == []


class TestUnknownKeysIgnored:
    def test_unknown_legacy_keys_ignored(self):
        state = {
            "legacy_blob": {"foo": "bar"},
            "mrr": 1000.0,
        }
        result = mission_state_to_ontology(state)
        assert isinstance(result, dict)
        assert "legacy_blob" not in result
        assert len(result["MoneyEvent"]) == 1

    def test_malformed_list_items_skipped_not_raised(self):
        state = {
            "parties": [
                {"id": "p1", "kind": "customer", "name": "Good",
                 "status": "active", "owner": None, "contact_points": [],
                 "notes": None, "source_refs": []},
                {"id": "p2", "kind": "customer", "name": "Bad",
                 "status": "active", "owner": None,
                 "contact_points": "not-a-list",  # wrong type -> rejected
                 "notes": None, "source_refs": []},
            ],
        }
        result = mission_state_to_ontology(state)
        assert len(result["Party"]) == 1
        assert result["Party"][0].id == "p1"


class TestEngagementStateAdapter:
    def test_engagement_state_maps_ontology_objects(self):
        state = {
            "engagement_id": "eng-1",
            "ontology_objects": {
                "Party": [
                    {"id": "p-1", "kind": "customer", "name": "Acme",
                     "status": "active", "owner": None, "contact_points": [],
                     "notes": None, "source_refs": []},
                ],
                "MoneyEvent": [
                    {"id": "m-1", "kind": "payable", "amount": 500.0,
                     "currency": "USD", "status": "open", "due_date": None,
                     "occurred_at": None, "counterparty_id": None,
                     "notes": None, "source_refs": []},
                ],
            },
        }
        result = engagement_state_to_ontology(state)
        assert len(result["Party"]) == 1
        assert len(result["MoneyEvent"]) == 1
        assert isinstance(result["Party"][0], Party)
        assert isinstance(result["MoneyEvent"][0], MoneyEvent)

    def test_engagement_state_empty(self):
        assert engagement_state_to_ontology({}) == {}
