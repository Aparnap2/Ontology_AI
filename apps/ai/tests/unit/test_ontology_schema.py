"""TDD tests for OntologyAI V5.1 — Ontology Schema Module (PRD §12).

These tests assert the six canonical Object Types and the 11 link types.
Run:
    cd /home/aparna/Desktop/iterate_swarm/apps/ai
    uv run pytest tests/unit/test_ontology_schema.py -v
"""
import pytest
from pydantic import ValidationError

from src.ontology.object_types import (
    Party,
    Engagement,
    MoneyEvent,
    Issue,
    Message,
    PlannedAction,
    OBJECT_TYPES,
)
from src.ontology.link_types import LINK_TYPES, resolve_link, LinkType


# ---------------------------------------------------------------------------
# Object Type: valid construction
# ---------------------------------------------------------------------------
class TestObjectTypeValidConstruction:
    def test_party_valid(self):
        p = Party(
            id="p-1", kind="customer", name="Acme", status="active",
            owner="alice", contact_points=["email:a@x.com"], notes=None,
            source_refs=["src1"],
        )
        assert p.id == "p-1"
        assert p.kind == "customer"

    def test_engagement_valid(self):
        e = Engagement(
            id="e-1", kind="deal", title="Big Deal", status="active",
            owner="bob", value=50000.0, due_date=None, notes=None,
            source_refs=[],
        )
        assert e.value == 50000.0

    def test_money_event_valid(self):
        m = MoneyEvent(
            id="m-1", kind="receivable", amount=1000.0, currency="USD",
            status="open", due_date=None, occurred_at=None,
            counterparty_id=None, notes=None, source_refs=[],
        )
        assert m.amount == 1000.0

    def test_issue_valid(self):
        i = Issue(
            id="i-1", kind="delay", severity="high", status="open",
            opened_at=None, resolved_at=None, owner=None,
            summary="Shipment delayed", notes=None, source_refs=[],
        )
        assert i.severity == "high"

    def test_message_valid(self):
        msg = Message(
            id="msg-1", channel="email", thread_id=None, timestamp=None,
            direction="inbound", summary="Asking about invoice",
            sentiment="neutral", needs_action=True, source_refs=[],
        )
        assert msg.needs_action is True

    def test_planned_action_valid(self):
        a = PlannedAction(
            id="a-1", type="create_note", title="Note", blast_radius="low",
            status="draft", requested_by="bob",
            target_object_type="Party", target_id="p-1", rationale="x",
            requires_approval=False, execution_payload=None, source_refs=[],
        )
        assert a.blast_radius == "low"


# ---------------------------------------------------------------------------
# Object Type: strict + extra="forbid" rejects unknown fields
# ---------------------------------------------------------------------------
class TestObjectTypeRejectsExtraFields:
    def test_party_rejects_extra(self):
        with pytest.raises(ValidationError):
            Party(
                id="p", kind="customer", name="X", status="active",
                owner=None, contact_points=[], notes=None, source_refs=[],
                surprise="boom",
            )

    def test_money_event_rejects_extra(self):
        with pytest.raises(ValidationError):
            MoneyEvent(
                id="m", kind="payable", amount=1.0, currency="USD",
                status="open", due_date=None, occurred_at=None,
                counterparty_id=None, notes=None, source_refs=[], extra=1,
            )

    def test_planned_action_rejects_extra(self):
        with pytest.raises(ValidationError):
            PlannedAction(
                id="a", type="x", title="t", blast_radius="low",
                status="draft", requested_by="bob",
                target_object_type="Party", target_id="p", rationale="r",
                requires_approval=False, execution_payload=None,
                source_refs=[], priority=1,
            )


# ---------------------------------------------------------------------------
# Object Type: strict typing rejects wrong types
# ---------------------------------------------------------------------------
class TestObjectTypeStrictTyping:
    def test_party_contact_points_wrong_type(self):
        with pytest.raises(ValidationError):
            Party(
                id="p", kind="customer", name="X", status="active",
                owner=None, contact_points="not-a-list", notes=None,
                source_refs=[],
            )

    def test_money_event_amount_wrong_type(self):
        with pytest.raises(ValidationError):
            MoneyEvent(
                id="m", kind="payable", amount="not-a-float", currency="USD",
                status="open", due_date=None, occurred_at=None,
                counterparty_id=None, notes=None, source_refs=[],
            )

    def test_planned_action_blast_radius_literal(self):
        with pytest.raises(ValidationError):
            PlannedAction(
                id="a", type="x", title="t", blast_radius="critical",
                status="draft", requested_by="bob",
                target_object_type="Party", target_id="p", rationale="r",
                requires_approval=False, execution_payload=None, source_refs=[],
            )

    def test_party_kind_literal(self):
        with pytest.raises(ValidationError):
            Party(
                id="p", kind="alien", name="X", status="active",
                owner=None, contact_points=[], notes=None, source_refs=[],
            )


# ---------------------------------------------------------------------------
# OBJECT_TYPES registry contains exactly the seven canonical types
# ---------------------------------------------------------------------------
class TestObjectTypeRegistry:
    def test_exactly_seven_types(self):
        assert set(OBJECT_TYPES.keys()) == {
            "Party", "Engagement", "MoneyEvent", "Issue", "Message",
            "PlannedAction", "Shipment",
        }


# ---------------------------------------------------------------------------
# LINK_TYPES registry — exactly 12 canonical links
# ---------------------------------------------------------------------------
class TestLinkTypesRegistry:
    EXPECTED = {
        "party_engagement", "engagement_money_event", "engagement_issue",
        "message_party", "message_engagement", "issue_planned_action",
        "money_event_planned_action", "party_planned_action",
        "engagement_planned_action", "workflow_action",
        "workflow_object_dependency", "order_shipment",
    }

    def test_all_twelve_present(self):
        assert set(LINK_TYPES.keys()) == self.EXPECTED

    def test_each_is_linktype_with_required_fields(self):
        for name, lt in LINK_TYPES.items():
            assert isinstance(lt, LinkType)
            assert lt.name == name
            assert lt.source_type
            assert lt.target_type
            assert lt.cardinality
            assert lt.semantic_meaning

    def test_party_engagement_link(self):
        lt = LINK_TYPES["party_engagement"]
        assert lt.source_type == "Party"
        assert lt.target_type == "Engagement"


# ---------------------------------------------------------------------------
# resolve_link helper
# ---------------------------------------------------------------------------
class FakeDB:
    def __init__(self, mapping=None):
        self._mapping = mapping or {}

    def fetch_links(self, source_type, source_id, link_name):
        return self._mapping.get((source_type, source_id, link_name), [])


class TestResolveLink:
    def test_unknown_link_raises_keyerror(self):
        with pytest.raises(KeyError):
            resolve_link("unknown_link", "x")

    def test_resolves_linked_ids_from_fake_db(self):
        fake_db = FakeDB({
            ("Party", "p-1", "party_engagement"): ["e-1", "e-2"],
        })
        result = resolve_link("party_engagement", "p-1", db=fake_db)
        assert result == ["e-1", "e-2"]

    def test_returns_empty_when_no_links(self):
        assert resolve_link("party_engagement", "p-99", db=FakeDB()) == []

    def test_callable_db_interface_accepted(self):
        def fake_fetch(source_type, source_id, link_name):
            return ["e-x"]
        assert resolve_link("party_engagement", "p-7", db=fake_fetch) == ["e-x"]
