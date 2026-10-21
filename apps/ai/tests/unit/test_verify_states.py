"""VerifyOutcome states — verification that can fail (Phase E P0).

Empty expectations fail closed (INDETERMINATE); partial matches are
distinguished from clean passes and clean misses; retryable transport
errors keep their retryability through verification.
"""
from __future__ import annotations

from src.mission.verify import (
    READ_COUNTERPART,
    VerifyOutcome,
    derive_expected,
    verify_write,
)


class FakeCaps:
    def __init__(self, records=None, error=None):
        self.records = records or []
        self.error = error

    def execute(self, op, params, tenant, role_caps=None):
        if self.error is not None:
            raise self.error
        return {"op": op, "ok": True, "data": list(self.records)}


async def test_empty_expected_fails_closed_indeterminate():
    """No predicates is not evidence of success."""
    outcome = await verify_write(
        "jira.update",
        {"issue_id": "P-1", "fields": {"status": "Done"}},
        {},
        "t1",
        capabilities=FakeCaps([{"key": "P-1", "status": "Done"}]),
    )
    assert outcome.verified is False
    assert outcome.state == "INDETERMINATE"


async def test_full_match_verified():
    outcome = await verify_write(
        "jira.update",
        {"issue_id": "P-1", "fields": {"status": "Done"}},
        {"status": "Done"},
        "t1",
        capabilities=FakeCaps([{"key": "P-1", "status": "Done"}]),
    )
    assert outcome.verified is True
    assert outcome.state == "VERIFIED"


async def test_partial_match_is_partial_not_pass():
    outcome = await verify_write(
        "jira.update",
        {"issue_id": "P-1", "fields": {"status": "Done"}},
        {"status": "Done", "assignee": "alice"},
        "t1",
        capabilities=FakeCaps([{"key": "P-1", "status": "Done"}]),
    )
    assert outcome.verified is False
    assert outcome.state == "PARTIALLY_VERIFIED"
    assert outcome.mismatch == "assignee"


async def test_no_record_not_verified():
    outcome = await verify_write(
        "jira.update",
        {"issue_id": "P-1", "fields": {"status": "Done"}},
        {"status": "Done"},
        "t1",
        capabilities=FakeCaps([]),
    )
    assert outcome.verified is False
    assert outcome.state == "NOT_VERIFIED"
    assert outcome.mismatch == "record"


async def test_retryable_error_stays_retryable():
    from src.connectors.jira_client import JiraTimeoutError

    outcome = await verify_write(
        "jira.update",
        {"issue_id": "P-1", "fields": {"status": "Done"}},
        {"status": "Done"},
        "t1",
        capabilities=FakeCaps(error=JiraTimeoutError("slow")),
    )
    assert outcome.verified is False
    assert outcome.state == "RETRYABLE_FAILURE"


async def test_terminal_error_not_verified():
    outcome = await verify_write(
        "jira.update",
        {"issue_id": "P-1", "fields": {"status": "Done"}},
        {"status": "Done"},
        "t1",
        capabilities=FakeCaps(error=RuntimeError("boom")),
    )
    assert outcome.verified is False
    assert outcome.state == "NOT_VERIFIED"


def test_historical_constructors_keep_meaning():
    """Old verified=True/False constructors map to VERIFIED/NOT_VERIFIED."""
    assert VerifyOutcome(verified=True).state == "VERIFIED"
    assert VerifyOutcome(verified=True).verified is True
    assert VerifyOutcome(verified=False).state == "NOT_VERIFIED"
    assert VerifyOutcome(state="INDETERMINATE").verified is False


def test_derive_expected_update_create_unknown():
    assert derive_expected("jira.update", {"issue_id": "P", "fields": {"status": "X"}}) == {
        "status": "X"
    }
    assert derive_expected("salesforce.update", {"record_id": "d", "fields": {"stage": "Y"}}) == {
        "stage": "Y"
    }
    assert derive_expected("jira.create", {"project": "P"}, result="PROJ-9") == {"key": "PROJ-9"}
    assert derive_expected("slack.send", {"channel": "c", "text": "hi"}) == {}
    assert "jira.create" in READ_COUNTERPART


async def test_jira_create_verifies_by_result_key():
    """Create-then-read-back uses the minted key, not write params."""
    outcome = await verify_write(
        "jira.create",
        {"project": "P", "summary": "s"},
        {"key": "PROJ-9"},
        "t1",
        capabilities=FakeCaps([{"key": "PROJ-9", "summary": "s"}]),
        result="PROJ-9",
    )
    assert outcome.verified is True
    assert outcome.state == "VERIFIED"
