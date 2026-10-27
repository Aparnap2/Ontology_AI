"""Jira hero client — schemas, error mapping, guards (offline unit).

Transport-level tests use httpx.MockTransport (no network). Live HTTP
against local Mockoon lives in tests/integration/test_jira_demo_binding.py.
"""
from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from src.connectors.jira_client import (
    CreateIssueRequest,
    JiraAuthError,
    JiraBadRequestError,
    JiraClient,
    JiraConnectionError,
    JiraNotFoundError,
    JiraRateLimitedError,
    JiraServerError,
    JiraTimeoutError,
    parse_issue,
)


def _client(handler, **over):
    transport = httpx.MockTransport(handler)
    kwargs = {"base_url": "http://localhost:3003", "tenant_id": "t1", "transport": transport}
    kwargs.update(over)
    return JiraClient(**kwargs)


def test_parse_issue_full_shape():
    issue = parse_issue({
        "key": "PROJ-1",
        "fields": {
            "summary": "SSO", "status": {"name": "Blocked"},
            "assignee": {"displayName": "Alice"}, "project": {"key": "PROJ"},
        },
    })
    assert (issue.key, issue.summary, issue.status, issue.assignee, issue.project_key) == (
        "PROJ-1", "SSO", "Blocked", "Alice", "PROJ",
    )


def test_parse_issue_partial_shape_never_crashes():
    issue = parse_issue({"key": "X-1"})
    assert issue.key == "X-1" and issue.status == "" and issue.assignee is None


def test_create_request_rejects_empty_project():
    with pytest.raises(ValidationError):
        CreateIssueRequest(project="", summary="s")


def test_tenant_scope_enforced():
    with pytest.raises(ValueError, match="tenant_id"):
        JiraClient(base_url="http://localhost:3003", tenant_id="  ")


def test_demo_binding_refuses_remote_host():
    with pytest.raises(ValueError, match="localhost"):
        JiraClient(base_url="https://jira.atlassian.net", tenant_id="t1", demo=True)


def test_get_issue_maps_shape():
    def handler(request):
        return httpx.Response(200, json={"key": "P-1", "fields": {"summary": "s", "status": {"name": "Done"}}})

    assert _client(handler).get_issue("P-1").status == "Done"


def test_error_mapping():
    cases = [
        (400, JiraBadRequestError, False),
        (401, JiraAuthError, False),
        (403, JiraAuthError, False),
        (404, JiraNotFoundError, False),
        (429, JiraRateLimitedError, True),
        (500, JiraServerError, True),
        (503, JiraServerError, True),
    ]
    for status, exc, retryable in cases:
        def handler(request, _status=status):
            return httpx.Response(_status, json={"error": "x"})

        with pytest.raises(exc):
            _client(handler).get_issue("P-1")
        try:
            _client(handler).get_issue("P-1")
        except exc as e:
            assert e.retryable is retryable
            assert e.status == status


def test_timeout_is_retryable():
    def handler(request):
        raise httpx.ConnectTimeout("slow")

    with pytest.raises(JiraTimeoutError) as info:
        _client(handler).get_issue("P-1")
    assert info.value.retryable is True


def test_connection_refused_is_retryable():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(JiraConnectionError) as info:
        _client(handler).get_issue("P-1")
    assert info.value.retryable is True


def test_link_builds_blocks_payload():
    seen: list[dict] = []

    def handler(request):
        seen.append({"url": str(request.url), "body": request.read().decode()})
        return httpx.Response(201, json={"linked": True})

    import json

    out = _client(handler).link_issues("PROJ-2", "PROJ-1")
    assert out == {"linked": True, "inward": "PROJ-2", "outward": "PROJ-1"}
    payload = json.loads(seen[0]["body"])
    assert payload["type"]["name"] == "Blocks"
    assert payload["inwardIssue"]["key"] == "PROJ-2"
    assert payload["outwardIssue"]["key"] == "PROJ-1"


def test_create_returns_key_and_validates():
    def handler(request):
        return httpx.Response(201, json={"id": "1", "key": "PROJ-9"})

    key = _client(handler).create_issue(
        {"project": "PROJ", "summary": "s", "description": "", "issue_type": "Task"}
    )
    assert key == "PROJ-9"
    with pytest.raises(Exception):
        _client(handler).create_issue({"project": "", "summary": "s"})


def test_create_without_key_fails_closed():
    def handler(request):
        return httpx.Response(201, json={"id": "1"})

    from src.connectors.jira_client import JiraClientError

    with pytest.raises(JiraClientError, match="no issue key"):
        _client(handler).create_issue({"project": "P", "summary": "s"})


def test_update_returns_merged_view():
    def handler(request):
        assert request.method == "PUT"
        return httpx.Response(204)

    assert _client(handler).update_issue("P-1", {"status": "Done"}) == {
        "id": "P-1", "status": "Done",
    }
