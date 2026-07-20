"""V5.1 OntologyAI pilot — REAL LLM (Groq/OpenRouter) end-to-end smoke test.

Run:
    cd apps/ai
    set -a; source ../.env; set +a
    uv run python scripts/pilot_v51_real_llm.py

Constraints: ONLY Groq/OpenRouter keys. Never OpenAI/Azure.
"""
from __future__ import annotations

import os
import sys

# Ensure repo root (apps/ai) is importable for `src.*` packages.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def banner(title: str) -> None:
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


def main() -> int:
    # ── 0. Environment / provider selection ────────────────────────────
    banner("0. Provider / Model Selection")
    from src.config.llm import get_llm_client, get_chat_model, _is_groq

    provider = "groq" if _is_groq() else (
        "openrouter" if os.environ.get("OPENROUTER_API_KEY") else "unknown"
    )
    model = get_chat_model()
    print(f"Active provider : {provider}")
    print(f"Active model    : {model}")
    if provider not in ("groq", "openrouter"):
        print("ERROR: no Groq/OpenRouter key present. Aborting live call.")
        return 2

    # ── 1. REAL LLM chat completion via factory ────────────────────────
    banner("1. Live LLM Chat Completion (factory)")
    try:
        client = get_llm_client()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say hello in one word."}],
            max_tokens=20,
            temperature=0.0,
        )
        text = resp.choices[0].message.content.strip()
        print(f"Response        : {text!r}")
        print(f"Finish reason   : {resp.choices[0].finish_reason}")
        print(f"Usage           : {resp.usage}")
    except Exception as e:  # noqa: BLE001
        print(f"LLM ERROR: {type(e).__name__}: {e}")
        return 1

    # ── 2. V5.1 offline compile path (ExecutableWorkflowDraft) ──────────
    banner("2. V5.1 n8n Compile (offline)")
    try:
        from src.ontology.workflow_drafts import ExecutableWorkflowDraft
        from src.runtime.n8n_compiler import compile_n8n

        draft = ExecutableWorkflowDraft(
            id="pilot-001",
            runtime="n8n",
            name="Pilot Workflow",
            source_workflow_spec_id="spec-pilot",
            trigger={"type": "schedule", "cron": "0 9 * * *"},
            steps=[
                {"id": "s1", "action": "fetch_metrics"},
                {"id": "s2", "action": "summarize"},
            ],
            decision_points=[{"id": "d1", "condition": "anomaly == true"}],
            success_criteria=["summary_generated"],
        )
        payload = compile_n8n(draft)
        print(f"Compiled nodes  : {len(payload['nodes'])}")
        print(f"Connections     : {len(payload['connections'])}")
        print(f"export_payload  : set via sanctioned setter = {draft.export_payload is not None}")
    except Exception as e:  # noqa: BLE001
        print(f"COMPILE ERROR: {type(e).__name__}: {e}")
        return 1

    # ── 3. Simple agent run (QAGraph — no Temporal/Redis/Qdrant) ────────
    banner("3. Agent Run (QAGraph.invoke)")
    try:
        from src.agents.qa.graph import QAGraph
        from src.agents.qa.state import QAState

        qa = QAGraph(tenant_id="pilot-tenant")
        state: QAState = {"tenant_id": "pilot-tenant", "question": "What is our MRR?"}
        result = qa.invoke(state)
        answer = result.get("answer", "")
        print(f"QA answer       : {answer[:160]}")
        if result.get("error"):
            print(f"QA error        : {result['error']}")
    except Exception as e:  # noqa: BLE001
        print(f"AGENT ERROR: {type(e).__name__}: {e}")
        print("Agent step skipped — see error above.")

    banner("PILOT COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
