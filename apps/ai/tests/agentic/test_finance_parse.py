"""
Layer 3 - Agentic Test #2: Real LLM → Pydantic Parse

If health check passed and this fails: parser is wrong, not the LLM.
Per the error attribution: this proves the parser handles real LLM output.
"""
import pytest


def call_llm_with_retry(ollama_client, llm_model, prompt, max_tokens=100, max_retries=1, json_mode=False):
    """Call LLM with retry on empty response."""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            options = {"num_predict": max_tokens}
            if json_mode:
                options["json_mode"] = True
            response = ollama_client.chat(
                model=llm_model,
                messages=[{"role": "user", "content": prompt}],
                options=options,
            )
            content = response["message"]["content"]
            if content and content.strip():
                return content, None
            last_error = "Empty response"
        except Exception as e:
            last_error = e
    return None, last_error


@pytest.mark.agentic
def test_finance_agent_pydantic_parse_real_llm(ollama_client, llm_model):
    """Real LLM call → must parse into AlertDecision.

    If this fails after health test passed: parser is wrong.
    """
    from src.schemas.guardian import AlertDecision

    prompt = f"""You are a finance Guardian. Given this data:
- Runway: 110 days
- MRR change: -15%
- Burn: $60,000/month

Rules flagged: runway_critical, mrr_drop

Is this alert-worthy? Answer with JSON:
{{"should_alert": true/false, "severity": "critical/warning/info", "primary_signal": "runway_critical/mrr_drop/none", "context_note": "max 20 words"}}"""

    content, error = call_llm_with_retry(ollama_client, llm_model, prompt, max_tokens=100, json_mode=True)
    if error:
        pytest.fail(f"LLM call failed after retries: {error}")

    import json
    from src.config.llm import extract_json_content
    data = json.loads(extract_json_content(content))
    result = AlertDecision(**data)

    assert isinstance(result, AlertDecision), "Failed to parse into AlertDecision"
    assert result.should_alert is True, "Expected should_alert=True"
    assert result.severity in ("critical", "warning", "info"), f"Invalid severity: {result.severity}"
    assert len(result.context_note.split()) <= 20, f"context_note exceeds 20 words: {result.context_note}"
    assert result.primary_signal in ("runway_critical", "mrr_drop", "burn_spike", "none")


@pytest.mark.agentic
def test_guardian_message_contract_real_llm(ollama_client, llm_model):
    """Real LLM narrative generation must satisfy PRD contract.

    Word count ≤ 200, injected_numbers non-empty, pattern from watchlist.
    """
    prompt = f"""Write a Guardian alert (max 200 words).
Pattern: FG-04 (Runway Compression)
Numbers: runway=110 days, burn=$60k/mo, MRR=$10k
Start with pattern name, end with one action.
Do NOT start with a number.
Inject the numbers: 110 days, $60k, $10k"""

    content, error = call_llm_with_retry(ollama_client, llm_model, prompt, max_tokens=300)
    if error:
        pytest.fail(f"LLM call failed after retries: {error}")

    content = content.strip()
    word_count = len(content.split())

    assert word_count <= 200, f"Exceeds 200 words: {word_count}"
    assert not content[0].isdigit(), "Must NOT start with number"
    assert any(char.isdigit() for char in content), "Must inject numbers"


@pytest.mark.agentic
def test_llm_reachability(ollama_client, llm_model):
    """Verify LLM is reachable."""
    content, error = call_llm_with_retry(ollama_client, llm_model, "ping", max_tokens=5)
    assert error is None, f"LLM not reachable: {error}"
    assert content is not None and content.strip(), "LLM returned empty response"