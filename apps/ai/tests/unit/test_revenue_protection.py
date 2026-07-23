"""TDD tests for Revenue Protection vertical slice — OntologyAI V5.1.

Tests the three parallel implementation tracks:
  1. ``Shipment`` object type + ``order_shipment`` link in the ontology
  2. ``_check_order_shipment_mismatch`` in ``TruthAnalysisWorkflow``
  3. ``explain_mismatch`` in the semantic layer (+ LLM fallback)

Run FIRST (RED phase) — then implement to make them GREEN.

Shipment schema
---------------
* ``Shipment`` is a Pydantic v2 model with ``extra="forbid"`` and ``strict=True``.
* Registered in ``OBJECT_TYPES`` under the key ``"Shipment"``.
* ``order_shipment`` link links ``Engagement`` (source) to ``Shipment`` (target)
  with ``one_to_many`` cardinality.

_check_order_shipment_mismatch (deterministic truth check)
----------------------------------------------------------
* Scans Engagements with ``kind="order"``.
* For each order, finds linked Shipments via ``order_shipment`` links.
* Computes shipped_total and compares to order.value.
* Delta ≤ 5% of order value → no finding.
* 5% < delta ≤ 15% → severity="medium".
* delta > 15% → severity="high".
* Under-shipped → kind includes ``under_shipped``.
* Over-shipped → kind includes ``over_shipped``.
* All findings are ``action_worthy=True`` with a ``details`` dict.

explain_mismatch (semantic layer)
---------------------------------
* Deterministic fallback when LLM is None.
* Uses LLM when a client with ``.predict()`` is available.
* Falls back to deterministic string if LLM raises.
"""
from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock

# Mock heavy external deps before ANY project-level import.
# The src.agents package imports all agents eagerly via __init__.py,
# which pulls in qdrant_client, temporalio, redis, aiokafka, etc.
import types as _types

for _mod_name in (
    "structlog",
    "qdrant_client",
    "qdrant_client.grpc",
    "qdrant_client.models",
    "temporalio",
    "temporalio.client",
    "temporalio.worker",
    "temporalio.activity",
    "temporalio.common",
    "redis",
    "redis.asyncio",
    "openai",
    "httpx",
    "aiokafka",
    "grpc",
    "grpc.aio",
    "langchain",
    "langchain_core",
    "langgraph",
    "dspy",
    "tiktoken",
    "sentence_transformers",
):
    sys.modules[_mod_name] = MagicMock()

# Wire module-level attributes that deeper code expects.
import structlog
structlog.get_logger.return_value = MagicMock()

import qdrant_client
qdrant_client.AsyncQdrantClient = MagicMock()
qdrant_client.QdrantClient = MagicMock()
qdrant_client.models.PointStruct = MagicMock()
qdrant_client.models.Filter = MagicMock()
qdrant_client.models.FilterSelector = MagicMock()
qdrant_client.models.Distance = MagicMock()
qdrant_client.models.VectorParams = MagicMock()

import temporalio
temporalio.client.Client = MagicMock()
temporalio.worker.Worker = MagicMock()
temporalio.activity = MagicMock()
temporalio.common.RetryPolicy = MagicMock()

import pytest

# ---------------------------------------------------------------------------
# Safe top-level imports — these modules have no external dependencies.
# ---------------------------------------------------------------------------
from src.ontology.object_types import OBJECT_TYPES, PlannedAction, Shipment
from src.ontology.link_types import LINK_TYPES


# ===========================================================================
# Helper factories (lazy workflow import to avoid agent __init__ cascade)
# ===========================================================================

def _make_workflow(llm=None):
    from src.workflows.truth_analysis_workflow import TruthAnalysisWorkflow
    return TruthAnalysisWorkflow(llm_client=llm)


def _get_explain_mismatch():
    """Lazy import to avoid triggering src.agents.__init__ at module level."""
    from src.agents.semantic_layer import explain_mismatch
    return explain_mismatch


def _order(eng_id: str, value: float, **overrides) -> dict[str, Any]:
    """Return an Engagement dict with kind='order'."""
    base = dict(
        id=eng_id,
        kind="order",
        title=f"Order {eng_id}",
        status="active",
        value=value,
        owner="bob",
        source_refs=["revpro-slice"],
    )
    base.update(overrides)
    return base


def _shipment(ship_id: str, order_id: str, shipped_value: float,
              status: str = "delivered", **overrides) -> dict[str, Any]:
    """Return a Shipment dict."""
    base = dict(
        id=ship_id,
        order_id=order_id,
        status=status,
        shipped_value=shipped_value,
        source_refs=["revpro-slice"],
    )
    base.update(overrides)
    return base


def _link(name: str, source_id: str, target_id: str) -> dict[str, str]:
    """Return a link dict."""
    return {"name": name, "source_id": source_id, "target_id": target_id}


# ===========================================================================
# Shipment Object Type schema + registry
# ===========================================================================

class TestShipmentObjectType:
    """Shipment Pydantic model and OBJECT_TYPES / LINK_TYPES registration."""

    def test_shipment_constructed_with_required_fields(self):
        """Shipment accepts only required fields."""
        s = Shipment(id="s1", order_id="e1", status="delivered",
                     shipped_value=500.0)
        assert s.id == "s1"
        assert s.order_id == "e1"
        assert s.status == "delivered"
        assert s.shipped_value == 500.0

    def test_shipment_rejects_extra_fields(self):
        """extra='forbid' prevents unknown fields."""
        with pytest.raises(Exception):  # pydantic.ValidationError
            Shipment(id="s2", order_id="e1", status="planned",
                     shipped_value=100.0, extra_field="bad")

    def test_shipment_serializes_to_dict(self):
        """model_dump() returns a plain dict with all fields."""
        s = Shipment(id="s3", order_id="e2", status="in_transit",
                     shipped_value=250.0, carrier="UPS",
                     items=[{"sku": "ABC", "qty": 2}])
        d = s.model_dump()
        assert d["id"] == "s3"
        assert d["order_id"] == "e2"
        assert d["status"] == "in_transit"
        assert d["shipped_value"] == 250.0
        assert d["carrier"] == "UPS"
        assert d["items"] == [{"sku": "ABC", "qty": 2}]

    def test_shipment_in_object_types_registry(self):
        """Shipment is registered in OBJECT_TYPES."""
        assert "Shipment" in OBJECT_TYPES
        assert OBJECT_TYPES["Shipment"] is Shipment

    def test_order_shipment_link_exists_with_correct_types(self):
        """order_shipment link: Engagement -> Shipment, one_to_many."""
        assert "order_shipment" in LINK_TYPES
        lt = LINK_TYPES["order_shipment"]
        assert lt.source_type == "Engagement"
        assert lt.target_type == "Shipment"
        assert lt.cardinality == "one_to_many"
        assert "revenue_protection_slice" in lt.source_refs

    def test_shipment_defaults_are_applied(self):
        """Optional fields have sensible defaults."""
        s = Shipment(id="s4", order_id="e3", status="returned",
                     shipped_value=0.0)
        assert s.items == []
        assert s.notes is None
        assert s.carrier is None
        assert s.shipped_at is None
        assert s.source_refs == []


# ===========================================================================
# _check_order_shipment_mismatch deterministic check
# ===========================================================================

class TestOrderShipmentMismatchCheck:
    """Deterministic truth-analysis check for Order <-> Shipment value mismatches.

    These tests call ``_check_order_shipment_mismatch`` directly (the private
    method on ``TruthAnalysisWorkflow``).  The method is expected to accept
    ``(ontology_objects: dict, ontology_links: list[dict])`` and return a list
    of finding dicts.
    """

    def test_no_orders_returns_empty_findings(self):
        """No Engagement with kind='order' -> empty list."""
        wf = _make_workflow()
        objs = {
            "Engagement": [{"id": "e1", "kind": "deal", "value": 1000.0}],
            "Shipment": [],
        }
        findings = wf._check_order_shipment_mismatch(objs, [])
        assert findings == []

    def test_perfect_match_no_finding(self):
        """Order value == shipped total -> no finding."""
        wf = _make_workflow()
        objs = {
            "Engagement": [_order("e1", 1000.0)],
            "Shipment": [_shipment("s1", "e1", 1000.0)],
        }
        links = [_link("order_shipment", "e1", "s1")]
        findings = wf._check_order_shipment_mismatch(objs, links)
        assert findings == []

    def test_under_shipped_returns_finding(self):
        """Order $1000, shipped $700 -> under_shipped finding."""
        wf = _make_workflow()
        objs = {
            "Engagement": [_order("e1", 1000.0)],
            "Shipment": [_shipment("s1", "e1", 700.0)],
        }
        links = [_link("order_shipment", "e1", "s1")]
        findings = wf._check_order_shipment_mismatch(objs, links)
        assert len(findings) == 1
        assert findings[0]["kind"] == "order_shipment_mismatch_under_shipped"

    def test_over_shipped_returns_finding(self):
        """Order $500, shipped $600 -> over_shipped finding."""
        wf = _make_workflow()
        objs = {
            "Engagement": [_order("e1", 500.0)],
            "Shipment": [_shipment("s1", "e1", 600.0)],
        }
        links = [_link("order_shipment", "e1", "s1")]
        findings = wf._check_order_shipment_mismatch(objs, links)
        assert len(findings) == 1
        assert findings[0]["kind"] == "order_shipment_mismatch_over_shipped"

    def test_within_five_percent_no_finding(self):
        """Delta <= 5% of order value -> no finding (small delta)."""
        wf = _make_workflow()
        # $1000 order, $980 shipped -> 2% delta -> within threshold
        objs = {
            "Engagement": [_order("e1", 1000.0)],
            "Shipment": [_shipment("s1", "e1", 980.0)],
        }
        links = [_link("order_shipment", "e1", "s1")]
        findings = wf._check_order_shipment_mismatch(objs, links)
        assert findings == []

    def test_multiple_shipments_totaling_correctly(self):
        """Three shipments sum to order value -> no finding."""
        wf = _make_workflow()
        objs = {
            "Engagement": [_order("e1", 1200.0)],
            "Shipment": [
                _shipment("s1", "e1", 500.0),
                _shipment("s2", "e1", 400.0),
                _shipment("s3", "e1", 300.0),
            ],
        }
        links = [
            _link("order_shipment", "e1", "s1"),
            _link("order_shipment", "e1", "s2"),
            _link("order_shipment", "e1", "s3"),
        ]
        findings = wf._check_order_shipment_mismatch(objs, links)
        assert findings == []

    def test_delta_over_fifteen_percent_severity_high(self):
        """Delta > 15% -> severity='high'."""
        wf = _make_workflow()
        objs = {
            "Engagement": [_order("e1", 1000.0)],
            "Shipment": [_shipment("s1", "e1", 500.0)],  # 50% delta
        }
        links = [_link("order_shipment", "e1", "s1")]
        findings = wf._check_order_shipment_mismatch(objs, links)
        assert len(findings) == 1
        assert findings[0]["severity"] == "high"

    def test_delta_between_five_and_fifteen_percent_severity_medium(self):
        """5% < delta <= 15% -> severity='medium'."""
        wf = _make_workflow()
        objs = {
            "Engagement": [_order("e1", 1000.0)],
            "Shipment": [_shipment("s1", "e1", 880.0)],  # 12% delta
        }
        links = [_link("order_shipment", "e1", "s1")]
        findings = wf._check_order_shipment_mismatch(objs, links)
        assert len(findings) == 1
        assert findings[0]["severity"] == "medium"

    def test_finding_is_action_worthy(self):
        """All order-shipment mismatch findings have action_worthy=True."""
        wf = _make_workflow()
        objs = {
            "Engagement": [_order("e1", 1000.0)],
            "Shipment": [_shipment("s1", "e1", 700.0)],
        }
        links = [_link("order_shipment", "e1", "s1")]
        findings = wf._check_order_shipment_mismatch(objs, links)
        assert len(findings) >= 1
        assert all(f.get("action_worthy") for f in findings)

    def test_finding_has_details_dict(self):
        """Finding includes details with order_value, shipped_total, delta, delta_pct."""
        wf = _make_workflow()
        objs = {
            "Engagement": [_order("e1", 1000.0)],
            "Shipment": [_shipment("s1", "e1", 700.0)],
        }
        links = [_link("order_shipment", "e1", "s1")]
        findings = wf._check_order_shipment_mismatch(objs, links)
        assert len(findings) == 1
        d = findings[0].get("details", {})
        assert d.get("order_value") == 1000.0
        assert d.get("shipped_total") == 700.0
        assert d.get("delta") == 300.0
        assert d.get("delta_pct") == 30.0

    def test_multiple_orders_only_mismatched_ones_returned(self):
        """Multiple orders; only the mismatched one produces a finding."""
        wf = _make_workflow()
        objs = {
            "Engagement": [
                _order("e1", 1000.0),   # perfect match -> no finding
                _order("e2", 500.0),    # under-shipped -> finding
            ],
            "Shipment": [
                _shipment("s1", "e1", 1000.0),
                _shipment("s2", "e2", 300.0),
            ],
        }
        links = [
            _link("order_shipment", "e1", "s1"),
            _link("order_shipment", "e2", "s2"),
        ]
        findings = wf._check_order_shipment_mismatch(objs, links)
        assert len(findings) == 1
        assert findings[0]["target_id"] == "e2"
        assert findings[0]["kind"] == "order_shipment_mismatch_under_shipped"

    def test_no_shipment_links_skips_order(self):
        """Order with no order_shipment links -> skipped (no finding)."""
        wf = _make_workflow()
        objs = {
            "Engagement": [_order("e1", 1000.0)],
            "Shipment": [_shipment("s1", "e1", 500.0)],
        }
        # No order_shipment link for e1
        findings = wf._check_order_shipment_mismatch(objs, [])
        assert findings == []

    def test_non_order_engagements_ignored(self):
        """Engagements with kind != 'order' are skipped."""
        wf = _make_workflow()
        objs = {
            "Engagement": [
                {"id": "e1", "kind": "deal", "value": 1000.0},
                _order("e2", 500.0),
            ],
            "Shipment": [_shipment("s1", "e2", 300.0)],
        }
        links = [_link("order_shipment", "e2", "s1")]
        findings = wf._check_order_shipment_mismatch(objs, links)
        assert len(findings) == 1
        assert findings[0]["target_id"] == "e2"

    def test_zero_value_order_skipped(self):
        """Order with value=0 is skipped to avoid division by zero."""
        wf = _make_workflow()
        objs = {
            "Engagement": [_order("e1", 0.0)],
            "Shipment": [_shipment("s1", "e1", 100.0)],
        }
        links = [_link("order_shipment", "e1", "s1")]
        findings = wf._check_order_shipment_mismatch(objs, links)
        assert findings == []


# ===========================================================================
# Semantic layer -- explain_mismatch
# ===========================================================================

class TestSemanticLayer:
    """explain_mismatch: deterministic fallback + optional LLM enrichment."""

    def test_explain_mismatch_no_llm_returns_deterministic_fallback(self):
        """Without an LLM client -> deterministic string (no exception)."""
        fn = _get_explain_mismatch()
        order = _order("e1", 1000.0)
        result = fn(
            order=order,
            shipment_count=1,
            shipped_total=700.0,
            delta=300.0,
            delta_pct=30.0,
            shipment_statuses=["delivered"],
            llm_client=None,
        )
        assert isinstance(result, str)
        assert len(result) > 0
        assert "Revenue risk" in result

    def test_explain_mismatch_with_llm_uses_llm(self):
        """With an LLM client that has .predict() -> uses LLM."""
        fn = _get_explain_mismatch()
        mock_llm = MagicMock()
        mock_llm.predict.return_value = "LLM generated explanation."

        order = _order("e1", 500.0)
        result = fn(
            order=order,
            shipment_count=1,
            shipped_total=600.0,
            delta=-100.0,
            delta_pct=20.0,
            shipment_statuses=["delivered"],
            llm_client=mock_llm,
        )
        assert result == "LLM generated explanation."
        mock_llm.predict.assert_called_once()

    def test_explain_mismatch_llm_throws_falls_back(self):
        """LLM client raises -> falls back to deterministic string."""
        fn = _get_explain_mismatch()
        mock_llm = MagicMock()
        mock_llm.predict.side_effect = RuntimeError("LLM unavailable")

        order = _order("e1", 1000.0)
        result = fn(
            order=order,
            shipment_count=1,
            shipped_total=700.0,
            delta=300.0,
            delta_pct=30.0,
            shipment_statuses=["delivered"],
            llm_client=mock_llm,
        )
        assert isinstance(result, str)
        assert "Revenue risk" in result
        mock_llm.predict.assert_called_once()

    def test_fallback_contains_under_shipped_direction(self):
        """Under-shipped fallback includes 'under_shipped'."""
        fn = _get_explain_mismatch()
        order = _order("e1", 1000.0)
        result = fn(
            order=order,
            shipment_count=1,
            shipped_total=700.0,
            delta=300.0,        # positive -> under_shipped
            delta_pct=30.0,
            shipment_statuses=["delivered"],
            llm_client=None,
        )
        assert "under_shipped" in result

    def test_fallback_contains_over_shipped_direction(self):
        """Over-shipped fallback includes 'over_shipped'."""
        fn = _get_explain_mismatch()
        order = _order("e1", 500.0)
        result = fn(
            order=order,
            shipment_count=2,
            shipped_total=600.0,
            delta=-100.0,       # negative -> over_shipped
            delta_pct=20.0,
            shipment_statuses=["delivered"],
            llm_client=None,
        )
        assert "over_shipped" in result

    def test_fallback_includes_dollar_amounts(self):
        """Fallback contains formatted dollar values."""
        fn = _get_explain_mismatch()
        order = _order("e1", 1000.0)
        result = fn(
            order=order,
            shipment_count=1,
            shipped_total=700.0,
            delta=300.0,
            delta_pct=30.0,
            shipment_statuses=["delivered"],
            llm_client=None,
        )
        assert "$1000.00" in result
        assert "$700.00" in result
        assert "30.0%" in result or "30%" in result

    def test_explain_mismatch_no_predict_method_uses_fallback(self):
        """LLM client without .predict() -> fallback."""
        fn = _get_explain_mismatch()
        mock_llm = MagicMock(spec=[])  # no methods
        # hasattr(llm_client, 'predict') will be False

        order = _order("e1", 1000.0)
        result = fn(
            order=order,
            shipment_count=1,
            shipped_total=700.0,
            delta=300.0,
            delta_pct=30.0,
            shipment_statuses=["delivered"],
            llm_client=mock_llm,
        )
        assert isinstance(result, str)
        assert "Revenue risk" in result

    def test_empty_shipment_statuses_in_fallback(self):
        """Fallback handles empty shipment_statuses gracefully."""
        fn = _get_explain_mismatch()
        order = _order("e1", 1000.0)
        result = fn(
            order=order,
            shipment_count=0,
            shipped_total=0.0,
            delta=1000.0,
            delta_pct=100.0,
            shipment_statuses=[],
            llm_client=None,
        )
        assert isinstance(result, str)
        assert "none" in result or len(result) > 0

    def test_fallback_recommendation_for_under_shipped(self):
        """Under-shipped fallback mentions follow-up on missing shipments."""
        fn = _get_explain_mismatch()
        order = _order("e1", 1000.0)
        result = fn(
            order=order,
            shipment_count=1,
            shipped_total=700.0,
            delta=300.0,
            delta_pct=30.0,
            shipment_statuses=["delivered"],
            llm_client=None,
        )
        assert "missing shipment" in result.lower()

    def test_fallback_recommendation_for_over_shipped(self):
        """Over-shipped fallback mentions review of over-shipment."""
        fn = _get_explain_mismatch()
        order = _order("e1", 500.0)
        result = fn(
            order=order,
            shipment_count=1,
            shipped_total=600.0,
            delta=-100.0,
            delta_pct=20.0,
            shipment_statuses=["delivered"],
            llm_client=None,
        )
        assert "over-shipment" in result.lower()


# ===========================================================================
# Candidate action mapping for order_shipment_mismatch findings
# ===========================================================================

class TestCandidateActionMapping:
    """_candidate_action handles order_shipment_mismatch_* finding kinds."""

    def test_candidate_action_for_under_shipped(self):
        """under_shipped kind -> returns a valid PlannedAction dict."""
        wf = _make_workflow()
        finding = {
            "kind": "order_shipment_mismatch_under_shipped",
            "target_type": "Engagement",
            "target_id": "e1",
            "severity": "high",
            "summary": "Order e1 value ($1000.00) != shipped total ($700.00)",
            "action_worthy": True,
            "details": {
                "order_value": 1000.0,
                "shipped_total": 700.0,
                "delta": 300.0,
                "delta_pct": 30.0,
            },
        }
        action = wf._candidate_action(finding, tenant_id="t1")
        assert action is not None
        # Must be a valid PlannedAction dict
        pa = PlannedAction(**action)
        assert pa.type is not None
        assert pa.target_id == "e1"
        assert pa.requested_by == "TruthAnalyst"
        # The kind name appears in source_refs, not rationale
        assert any(
            "order_shipment_mismatch_under_shipped" in ref
            for ref in pa.source_refs
        )

    def test_candidate_action_for_over_shipped(self):
        """over_shipped kind -> returns a valid PlannedAction dict."""
        wf = _make_workflow()
        finding = {
            "kind": "order_shipment_mismatch_over_shipped",
            "target_type": "Engagement",
            "target_id": "e2",
            "severity": "medium",
            "summary": "Order e2 value ($500.00) != shipped total ($600.00)",
            "action_worthy": True,
            "details": {
                "order_value": 500.0,
                "shipped_total": 600.0,
                "delta": -100.0,
                "delta_pct": 20.0,
            },
        }
        action = wf._candidate_action(finding, tenant_id="t1")
        assert action is not None
        pa = PlannedAction(**action)
        assert pa.target_id == "e2"
        assert pa.requested_by == "TruthAnalyst"

    def test_candidate_action_for_unmapped_kind_still_returns_action(self):
        """An unknown kind is handled gracefully (not a crash)."""
        wf = _make_workflow()
        finding = {
            "kind": "some_unmapped_finding",
            "target_type": "Engagement",
            "target_id": "e99",
            "severity": "low",
            "summary": "Unknown kind",
            "action_worthy": True,
        }
        action = wf._candidate_action(finding, tenant_id="t1")
        # Should still produce an action (defaulting to create_draft_action)
        assert action is not None
        pa = PlannedAction(**action)
        assert pa.type is not None
