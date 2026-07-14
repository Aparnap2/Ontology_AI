"""TDD tests for OntologyAI V4.2 — Ontology Schema Module (Task 1).

These tests are written FIRST and must FAIL until the schema modules
under ``apps/ai/src/ontology/`` are implemented.

Run:
    cd /home/aparna/Desktop/iterate_swarm/apps/ai
    uv run pytest tests/unit/test_ontology_schema.py -v
"""
import pytest
from datetime import datetime
from pydantic import ValidationError

from src.ontology.object_types import (
    Customer,
    Deal,
    RevenueMetric,
    Incident,
    Message,
    PlannedAction,
)
from src.ontology.link_types import LINK_TYPES, resolve_link


# ---------------------------------------------------------------------------
# Object Type: valid construction
# ---------------------------------------------------------------------------
class TestObjectTypeValidConstruction:
    """Each Object Type must construct a valid instance without error."""

    def test_customer_valid(self):
        c = Customer(
            id="cust-1",
            name="Acme Corp",
            mrr=1200.0,
            health_score=0.85,
            last_contact_at=datetime(2026, 7, 1, 12, 0, 0),
        )
        assert c.id == "cust-1"
        assert c.mrr == 1200.0

    def test_customer_optional_last_contact_none(self):
        c = Customer(
            id="cust-2",
            name="Globex",
            mrr=300.0,
            health_score=0.4,
            last_contact_at=None,
        )
        assert c.last_contact_at is None

    def test_deal_valid(self):
        d = Deal(
            id="deal-1",
            stage="negotiation",
            value=50000.0,
            close_probability=0.6,
            owner="alice",
        )
        assert d.stage == "negotiation"
        assert d.value == 50000.0

    def test_revenue_metric_valid(self):
        r = RevenueMetric(
            period="2026-07",
            mrr=90000.0,
            burn=40000.0,
            runway_days=18,
        )
        assert r.runway_days == 18
        assert isinstance(r.runway_days, int)

    def test_incident_valid(self):
        i = Incident(
            id="inc-1",
            severity="high",
            opened_at=datetime(2026, 7, 10, 9, 0, 0),
            resolved_at=None,
            root_cause="db failover",
        )
        assert i.severity == "high"
        assert i.resolved_at is None

    def test_message_valid(self):
        m = Message(
            id="msg-1",
            channel="slack",
            thread_id="thread-9",
            sentiment="positive",
            drafted_by="bot",
        )
        assert m.channel == "slack"

    def test_planned_action_valid(self):
        a = PlannedAction(
            id="act-1",
            type="refund",
            blast_radius="low",
            status="pending",
            requested_by="bob",
        )
        assert a.blast_radius == "low"


# ---------------------------------------------------------------------------
# Object Type: strict + extra="forbid" rejects unknown fields
# ---------------------------------------------------------------------------
class TestObjectTypeRejectsExtraFields:
    """Strict models must reject unknown/extra fields with ValidationError."""

    def test_customer_rejects_extra(self):
        with pytest.raises(ValidationError):
            Customer(
                id="cust-3",
                name="Initech",
                mrr=100.0,
                health_score=0.5,
                last_contact_at=None,
                unknown_field="boom",
            )

    def test_deal_rejects_extra(self):
        with pytest.raises(ValidationError):
            Deal(
                id="deal-2",
                stage="lead",
                value=10.0,
                close_probability=0.1,
                owner="carol",
                extra="nope",
            )

    def test_revenue_metric_rejects_extra(self):
        with pytest.raises(ValidationError):
            RevenueMetric(
                period="2026-08",
                mrr=1.0,
                burn=1.0,
                runway_days=1,
                surprise=True,
            )

    def test_incident_rejects_extra(self):
        with pytest.raises(ValidationError):
            Incident(
                id="inc-2",
                severity="low",
                opened_at=datetime(2026, 7, 1),
                resolved_at=None,
                root_cause="x",
                note="extra",
            )

    def test_message_rejects_extra(self):
        with pytest.raises(ValidationError):
            Message(
                id="msg-2",
                channel="email",
                thread_id="t",
                sentiment="neutral",
                drafted_by="human",
                spam=False,
            )

    def test_planned_action_rejects_extra(self):
        with pytest.raises(ValidationError):
            PlannedAction(
                id="act-2",
                type="email",
                blast_radius="medium",
                status="done",
                requested_by="dan",
                priority=1,
            )


# ---------------------------------------------------------------------------
# Object Type: strict typing rejects wrong types
# ---------------------------------------------------------------------------
class TestObjectTypeStrictTyping:
    """Strict mode must reject type-coercion of wrong types."""

    def test_customer_mrr_wrong_type(self):
        with pytest.raises(ValidationError):
            Customer(
                id="cust-4",
                name="Umbrella",
                mrr="not-a-float",  # strict: no coercion
                health_score=0.5,
                last_contact_at=None,
            )

    def test_revenue_metric_runway_wrong_type(self):
        with pytest.raises(ValidationError):
            RevenueMetric(
                period="2026-09",
                mrr=1.0,
                burn=1.0,
                runway_days="eighteen",  # strict: must be int
            )

    def test_planned_action_blast_radius_literal(self):
        with pytest.raises(ValidationError):
            PlannedAction(
                id="act-3",
                type="call",
                blast_radius="critical",  # not in Literal set
                status="pending",
                requested_by="eve",
            )


# ---------------------------------------------------------------------------
# LINK_TYPES registry
# ---------------------------------------------------------------------------
class TestLinkTypesRegistry:
    """LINK_TYPES must contain exactly the four specified links."""

    def test_all_four_links_present(self):
        assert "incident_affects_customer" in LINK_TYPES
        assert "deal_belongs_to_customer" in LINK_TYPES
        assert "message_relates_to_deal" in LINK_TYPES
        assert "action_targets_object" in LINK_TYPES

    def test_cardinality_strings(self):
        assert LINK_TYPES["incident_affects_customer"][2] == "many_to_many"
        assert LINK_TYPES["deal_belongs_to_customer"][2] == "many_to_one"
        assert LINK_TYPES["message_relates_to_deal"][2] == "many_to_one"
        assert LINK_TYPES["action_targets_object"][2] == "polymorphic"

    def test_source_target_types(self):
        assert LINK_TYPES["incident_affects_customer"][0] == "Incident"
        assert LINK_TYPES["incident_affects_customer"][1] == "Customer"
        assert LINK_TYPES["deal_belongs_to_customer"] == (
            "Deal",
            "Customer",
            "many_to_one",
        )
        assert LINK_TYPES["message_relates_to_deal"] == (
            "Message",
            "Deal",
            "many_to_one",
        )
        assert LINK_TYPES["action_targets_object"] == (
            "PlannedAction",
            "*",
            "polymorphic",
        )


# ---------------------------------------------------------------------------
# resolve_link helper
# ---------------------------------------------------------------------------
class FakeDB:
    """Minimal mock of the db interface expected by resolve_link.

    Expected interface: an object exposing
        fetch_links(source_type: str, source_id: str, link_name: str) -> list[str]
    """

    def __init__(self, mapping=None):
        self._mapping = mapping or {}

    def fetch_links(self, source_type, source_id, link_name):
        return self._mapping.get((source_type, source_id, link_name), [])


class TestResolveLink:
    """resolve_link queries the (injectable) db for linked object IDs."""

    def test_unknown_link_raises_keyerror(self):
        with pytest.raises(KeyError):
            resolve_link("unknown_link", "x")

    def test_resolves_linked_ids_from_fake_db(self):
        fake_db = FakeDB(
            {
                ("Deal", "deal-1", "deal_belongs_to_customer"): ["cust-1", "cust-2"],
            }
        )
        result = resolve_link("deal_belongs_to_customer", "deal-1", db=fake_db)
        assert result == ["cust-1", "cust-2"]

    def test_returns_empty_when_no_links(self):
        fake_db = FakeDB()
        result = resolve_link("deal_belongs_to_customer", "deal-99", db=fake_db)
        assert result == []

    def test_callable_db_interface_accepted(self):
        def fake_fetch(source_type, source_id, link_name):
            return ["cust-x"]

        result = resolve_link("deal_belongs_to_customer", "deal-7", db=fake_fetch)
        assert result == ["cust-x"]
