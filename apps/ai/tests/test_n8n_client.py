"""Unit tests for the real n8n REST client (mocked transport, no live n8n)."""

from __future__ import annotations

import json

import httpx
import pytest

from src.runtime import n8n_client
from src.ontology.workflow_drafts import ExecutableWorkflowDraft


def _mock_client(json_body: dict, status: int = 200) -> httpx.Client:
    """Return an httpx.Client whose post/patch/get return a fixed response."""
    transport = httpx.MockTransport(
        lambda req: httpx.Response(status, json=json_body)
    )
    return httpx.Client(transport=transport, verify=False)


def _sample_draft() -> ExecutableWorkflowDraft:
    return ExecutableWorkflowDraft(
        id="d1",
        runtime="n8n",
        name="Pilot Flow",
        source_workflow_spec_id="spec1",
        trigger={"rule": {"interval": [{"field": "cronExpression", "expression": "0 * * * *"}]}},
        steps=[{"id": "s1", "action": "log"}],
        success_criteria=["done"],
    )


def test_create_workflow_posts_to_rest_endpoint():
    cli = _mock_client({"id": "wf-123", "name": "Pilot Flow"})
    resp = n8n_client.create_workflow({"name": "x", "nodes": [], "connections": {}}, client=cli)
    assert resp["id"] == "wf-123"


def test_create_workflow_raises_on_error():
    cli = _mock_client({"message": "bad"}, status=400)
    with pytest.raises(n8n_client.N8nClientError):
        n8n_client.create_workflow({"name": "x"}, client=cli)


def test_compile_and_deploy_uses_sanctioned_compiler():
    created = {"id": "wf-999"}
    cli = _mock_client(created)

    draft = _sample_draft()
    result = n8n_client.compile_and_deploy(draft, client=cli)

    assert result["workflow_id"] == "wf-999"
    # payload was produced by the deterministic compiler and stored on the draft.
    assert draft.export_payload is not None
    assert draft.export_payload["name"] == "Pilot Flow"
    assert len(draft.export_payload["nodes"]) >= 3  # trigger + step + success
    assert "connections" in draft.export_payload


def test_healthcheck_true_when_reachable():
    cli = _mock_client({"data": []})
    assert n8n_client.healthcheck(client=cli) is True


def test_healthcheck_false_on_http_error():
    transport = httpx.MockTransport(lambda req: (_ for _ in ()).throw(httpx.ConnectError("boom")))
    cli = httpx.Client(transport=transport, verify=False)
    assert n8n_client.healthcheck(client=cli) is False
