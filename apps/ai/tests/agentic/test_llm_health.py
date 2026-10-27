"""
Layer 3 - Agentic Test #1: LLM API Health Check

This MUST pass before any other agentic test runs.
If this fails: LLM API is down, NOT the parser or agent.
Per the error attribution: this proves API health before testing parsing.
"""
import pytest


# CORRECTION (issue #71): these are LIVE-MODEL tests and were unmarked,
# so they executed inside the deterministic gate and failed with HTTP 401
# when credentials were stripped. Marked `llm` for the same reason as the
# other eight suites: a live-model suite is not a deterministic test.

pytestmark = [
    pytest.mark.llm,
]
@pytest.mark.agentic
def test_llm_api_health(ollama_client, llm_model):
    """Health check: LLM API is reachable before any agent test runs.

    This test proves the LLM API is healthy.
    If this fails → LLM API is down, not your code.
    """
    response = ollama_client.chat(
        model=llm_model,
        messages=[{"role": "user", "content": "ping"}],
        options={"num_predict": 5},
    )

    assert response["message"]["content"] is not None


@pytest.mark.agentic
def test_llm_response_time_sla(ollama_client, llm_model):
    """Verify LLM response time is within SLA."""
    import time
    start = time.time()

    response = ollama_client.chat(
        model=llm_model,
        messages=[{"role": "user", "content": "Say 'ok'"}],
        options={"num_predict": 5},
    )

    elapsed = time.time() - start

    assert elapsed < 10.0, f"LLM response took {elapsed:.2f}s, exceeds 10s SLA"
    assert response["message"]["content"] is not None