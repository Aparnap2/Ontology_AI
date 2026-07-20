"""Tests for the canonical 12-node workflow vocabulary (PRD §7)."""

from src.workflow_drafts.nodes import (
    NODE_KINDS,
    all_node_kinds,
    get_node_kind,
)

EXPECTED_12 = {
    "trigger.manual",
    "trigger.schedule",
    "trigger.webhook",
    "action.http",
    "action.llm",
    "action.db_query",
    "action.db_write",
    "action.transform",
    "action.code",
    "logic.branch",
    "logic.merge",
    "io.notify",
}


def test_exactly_twelve_kinds():
    assert len(NODE_KINDS) == 12
    assert set(all_node_kinds()) == EXPECTED_12


def test_each_kind_has_category_and_n8n_mapping():
    for kind in EXPECTED_12:
        nk = get_node_kind(kind)
        assert nk.category in ("trigger", "action", "logic", "io")
        mapping = nk.to_n8n()
        assert mapping["type"], f"{kind} missing n8n type"
        assert mapping["required_fields"] is not None


def test_categories_balanced():
    cats = [nk.category for nk in NODE_KINDS.values()]
    assert cats.count("trigger") == 3
    assert cats.count("action") == 6
    assert cats.count("logic") == 2
    assert cats.count("io") == 1
