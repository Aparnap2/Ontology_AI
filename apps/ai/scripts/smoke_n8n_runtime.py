"""V5.1 OntologyAI — Docker smoke test for the INVISIBLE n8n runtime.

Proves the managed n8n runtime works end-to-end via the internal Docker
network (http://n8n:5678) with NO host port exposure and NO real LLM.

Run INSIDE a container on the `iterateswarm-net` network, e.g.:

    docker run --rm --network iterateswarm-net \
      -v "$PWD/apps/ai:/app" -w /app \
      -e N8N_API_URL=http://n8n:5678/api/v1 \
      -e N8N_API_KEY=<key> \
      python:3.13 bash -c "pip install --quiet httpx pydantic && python scripts/smoke_n8n_runtime.py"

The script uses the real client (src.runtime.n8n_client.compile_and_deploy),
which POSTs to the live n8n REST API (POST /rest/workflows/). It then verifies
the workflow is actually listed via GET /rest/workflows.
"""

from __future__ import annotations

import os
import sys

import httpx

# Ensure the repo root (apps/ai) is importable for `src.*`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ontology.workflow_drafts import ExecutableWorkflowDraft  # noqa: E402
from src.runtime.n8n_client import compile_and_deploy  # noqa: E402


def main() -> int:
    api_url = os.environ.get("N8N_API_URL", "http://n8n:5678/api/v1").rstrip("/")
    api_key = os.environ.get("N8N_API_KEY")
    if not api_key:
        print("ERROR: N8N_API_KEY env not set", file=sys.stderr)
        return 2

    print(f"[smoke] target n8n API: {api_url}")

    draft = ExecutableWorkflowDraft(
        id="smoke",
        runtime="n8n",
        name="Smoke Flow",
        source_workflow_spec_id="s",
        trigger={
            "rule": {
                "interval": [
                    {"field": "cronExpression", "expression": "0 * * * *"}
                ]
            }
        },
        steps=[{"id": "a", "action": "noop"}],
        success_criteria=["ok"],
    )

    # Real, live call to n8n over the internal Docker network.
    result = compile_and_deploy(draft, activate=True, api_url=api_url)
    workflow_id = result.get("workflow_id")
    assert workflow_id, f"n8n returned no workflow id: {result}"
    print(f"[smoke] CREATED workflow id={workflow_id!r} name={draft.name!r}")

    # Independent verification: list workflows via GET /rest/workflows.
    headers = {"accept": "application/json", "X-N8N-API-KEY": api_key}
    resp = httpx.get(f"{api_url}/rest/workflows", headers=headers, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    found = [
        w
        for w in data.get("data", [])
        if str(w.get("id")) == str(workflow_id) or w.get("name") == draft.name
    ]
    assert found, f"workflow {workflow_id} NOT found in GET /rest/workflows listing"
    print(
        f"[smoke] VERIFIED: 'Smoke Flow' present in listing "
        f"(id={found[0]['id']}, active={found[0].get('active')})"
    )
    print(f"WORKFLOW_ID={workflow_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
