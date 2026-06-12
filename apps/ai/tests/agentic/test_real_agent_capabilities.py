"""
Real Agentic LLM Tests - Verify LLM Can Execute Agent Logic

These tests verify the LLM can execute actual agent logic, not just respond to chat:
1. Parse financial data and detect anomalies (Finance Guardian logic)
2. Make decisions following PRD rules (Phase 2: Cognitive Decision)
3. Generate compliant Guardian messages (Phase 3: Narrative)
4. Respect Pydantic contracts

Run with:
    export OLLAMA_BASE_URL="http://localhost:11434"
    export LLM_MODEL="qwen3-next:80b-cloud"
    python -m pytest tests/agentic/test_real_agent_capabilities.py -v
"""
import json
import os
import pytest
from pydantic import ValidationError

from src.schemas.guardian import AlertDecision, GuardianMessage


def call_llm(ollama_client, llm_model, prompt, max_tokens=500, temperature=0.0):
    """Call LLM and return content."""
    options = {"num_predict": max_tokens, "json_mode": True}
    if temperature != 0.0:
        options["temperature"] = temperature

    response = ollama_client.chat(
        model=llm_model,
        messages=[{"role": "user", "content": prompt}],
        options=options,
    )
    return response["message"]["content"].strip()


def parse_json_response(content):
    """Parse JSON from LLM response, handling markdown and thinking blocks."""
    from src.config.llm import extract_json_content

    try:
        return json.loads(extract_json_content(content))
    except json.JSONDecodeError as e:
        pytest.fail(f"LLM didn't return valid JSON: {e}\nContent: {content}")


# ============================================================================
# Test 1: Financial Anomaly Detection - LLM parses data and applies rules
# ============================================================================

@pytest.mark.agentic
def test_llm_detects_financial_anomaly(ollama_client, llm_model):
    """
    LLM should identify 'runway < 180 days' as critical from raw financial data.

    This tests actual Finance Guardian anomaly detection capability:
    - Parse raw financial metrics (MRR, Burn, Bank Balance, Churn)
    - Apply PRD rules to detect anomalies
    - Output structured JSON with anomalies and severity

    Expected: runway_days = 220000 / 60000 = 3.67 months ≈ 110 days < 180 → CRITICAL
    """
    prompt = """
    You are a Finance Guardian agent. Analyze the following financial data
    and detect anomalies using these PRD rules:

    RULES:
    1. If runway < 180 days → flag as CRITICAL
    2. If burn > 2x MRR growth → flag as WARNING (use growth_rate = 0.05 as placeholder)
    3. If monthly_churn_pct > 3% → flag as WARNING

    DATA:
    - MRR: $10,000
    - Burn: $60,000/month
    - Bank balance: $220,000
    - Monthly churn: 2%

    Compute:
    - runway_days = bank_balance / burn_rate
    - burn_multiple = burn_rate / mrr (if mrr > 0)

    OUTPUT JSON with exactly these keys:
    {
        "anomalies": ["list of pattern IDs like FG-04"],
        "severity": "critical|warning|info",
        "runway_days": computed value,
        "reasoning": "brief explanation"
    }

    Respond ONLY with valid JSON, no markdown or explanation.
    """

    content = call_llm(ollama_client, llm_model, prompt, max_tokens=500)
    print(f"\n[LLM Response]\n{content}")

    result = parse_json_response(content)

    assert "anomalies" in result, "Missing 'anomalies' key"
    assert "FG-04" in result["anomalies"] or "runway" in str(result.get("reasoning", "")).lower(), \
        f"LLM failed to detect runway compression. Result: {result}"

    assert result.get("runway_days", 0) < 180, \
        f"Runway should be < 180 days (got {result.get('runway_days')})"

    assert result.get("severity") == "critical", \
        f"Runway < 180 days should be 'critical', got {result.get('severity')}"


# ============================================================================
# Test 2: Phase 2 - Cognitive Decision - LLM respects Pydantic schema
# ============================================================================

@pytest.mark.agentic
def test_llm_respects_pydantic_schema(ollama_client, llm_model):
    """
    LLM output must parse into AlertDecision schema.
    Tests that LLM can follow structured output requirements.

    This is Phase 2: COGNITIVE DECISION - The LLM must output
    should_alert (bool), severity, primary_signal, context_note (max 20 words)
    """
    prompt = """
    You are a Guardian Agent making a cognitive decision.

    Context: Finance Guardian detected FG-04 (Runway Compression Acceleration)
    Financial data: runway_days=110, burn_rate=$60k/mo, bank_balance=$220k

    Output a JSON object matching this Pydantic schema:

    {
        "should_alert": true|false,
        "severity": "critical"|"warning"|"info",
        "primary_signal": "short name of the signal",
        "context_note": "brief context, MAX 20 WORDS"
    }

    Rules:
    - should_alert: true if any anomaly detected
    - severity: critical if runway < 180
    - primary_signal: include pattern ID (FG-04)
    - context_note: max 20 words

    Respond ONLY with valid JSON, no markdown.
    """

    content = call_llm(ollama_client, llm_model, prompt, max_tokens=300)
    print(f"\n[LLM Response]\n{content}")

    decision_data = parse_json_response(content)

    try:
        decision = AlertDecision(**decision_data)
    except ValidationError as e:
        pytest.fail(f"LLM output failed Pydantic validation:\n{e}\nData: {decision_data}")

    assert decision.should_alert is True, "Should alert for FG-04"
    assert decision.severity == "critical", "Runway < 180 days is critical"
    assert "FG-04" in decision.primary_signal or "runway" in decision.primary_signal.lower()


# ============================================================================
# Test 3: Phase 3 - Narrative Generation - LLM generates valid GuardianMessage
# ============================================================================

@pytest.mark.agentic
def test_llm_generates_valid_guardian_message(ollama_client, llm_model):
    """
    LLM must generate message that satisfies PRD contract:
    - Max 200 words
    - Start with pattern name (not number)
    - End with one action (no conjunctions)
    - Include injected_numbers audit trail

    This is Phase 3: NARRATIVE GENERATION
    """
    prompt = """
    You are a Guardian Agent generating a human-readable alert.

    PATTERN: FG-04 (Runway Compression Acceleration)
    DATA:
    - runway_days: 110 (was 200 last month)
    - burn_rate: $60,000/month
    - bank_balance: $220,000
    - severity: critical

    PRD REQUIREMENTS:
    1. pattern_name: Name only (e.g., "runway_compression"), NOT "FG-04"
    2. insight: Max 200 words, include the actual numbers
    3. urgency_horizon: "today" | "this_week" | "this_month" | "this_quarter"
    4. one_action: Exactly ONE action (no "and", no ";", no "then")
    5. injected_numbers: List the numbers from data [110, 60, 220]

    Output JSON:
    {
        "pattern_name": "...",
        "insight": "...",
        "urgency_horizon": "...",
        "one_action": "...",
        "injected_numbers": [...]
    }

    Respond ONLY with valid JSON, no markdown.
    """

    content = call_llm(ollama_client, llm_model, prompt, max_tokens=400)
    print(f"\n[LLM Response]\n{content}")

    message_data = parse_json_response(content)

    if "injected_numbers" in message_data:
        message_data["injected_numbers"] = [
            str(n) if isinstance(n, int) else n for n in message_data["injected_numbers"]
        ]

    try:
        guardian_msg = GuardianMessage(**message_data)
    except ValidationError as e:
        pytest.fail(f"LLM output failed GuardianMessage validation:\n{e}\nData: {message_data}")

    assert not guardian_msg.pattern_name.startswith("FG-"), \
        "pattern_name must be name, not ID"

    assert len(guardian_msg.insight.split()) <= 200, \
        f"insight must be max 200 words, got {len(guardian_msg.insight.split())}"

    conjunctions = [" and ", ";", " then ", " after that ", " also "]
    for conj in conjunctions:
        assert conj.lower() not in guardian_msg.one_action.lower(), \
            f"one_action must be ONE action, found '{conj}'"

    assert len(guardian_msg.injected_numbers) > 0, \
        "injected_numbers must not be empty"


# ============================================================================
# Test 4: Full Thin LLM Pattern - Verify Phase 1/2/3 Flow
# ============================================================================

@pytest.mark.agentic
def test_llm_phase1_phase2_phase3_flow(ollama_client, llm_model):
    """
    Test full Thin LLM pattern:

    Phase 1: DATA ASSEMBLY (should NOT call LLM - pure code)
    - This test verifies the DATA exists before LLM is called

    Phase 2: COGNITIVE DECISION (1 LLM call with typed input)
    - LLM receives typed financial data
    - Returns AlertDecision

    Phase 3: NARRATIVE (1 LLM call, bounded output)
    - LLM generates GuardianMessage with constraints
    """

    financial_data = {
        "mrr": 10000,
        "burn_rate": 60000,
        "bank_balance": 220000,
        "monthly_churn_pct": 2.0,
    }

    runway_days = financial_data["bank_balance"] / financial_data["burn_rate"] * 30
    burn_multiple = financial_data["burn_rate"] / financial_data["mrr"] if financial_data["mrr"] > 0 else 0

    detected_patterns = []
    if runway_days < 180:
        detected_patterns.append("FG-04")
    if financial_data["monthly_churn_pct"] > 3:
        detected_patterns.append("FG-01")
    if burn_multiple > 2:
        detected_patterns.append("FG-02")

    print(f"\n[Phase 1 - Pure Python Data Assembly]")
    print(f"  runway_days: {runway_days:.0f}")
    print(f"  burn_multiple: {burn_multiple:.1f}")
    print(f"  detected_patterns: {detected_patterns}")

    assert len(detected_patterns) > 0, "Phase 1 should detect at least one pattern"

    prompt_phase2 = f"""
    You are Phase 2: COGNITIVE DECISION

    Data from Phase 1 (typed input):
    - runway_days: {runway_days:.0f}
    - burn_multiple: {burn_multiple:.1f}
    - monthly_churn_pct: {financial_data['monthly_churn_pct']}
    - detected_patterns: {detected_patterns}

    Rules:
    - If runway_days < 180 → severity = "critical"
    - If burn_multiple > 2 → severity = "critical"
    - If detected_patterns has content → should_alert = true

    Output JSON:
    {{
        "should_alert": true|false,
        "severity": "critical"|"warning"|"info",
        "primary_signal": "FG-XX pattern",
        "context_note": "MAX 20 WORDS"
    }}

    Respond ONLY with valid JSON.
    """

    content_p2 = call_llm(ollama_client, llm_model, prompt_phase2, max_tokens=200)
    print(f"\n[Phase 2 - LLM Cognitive Decision]\n{content_p2}")

    try:
        decision = AlertDecision(**parse_json_response(content_p2))
    except ValidationError as e:
        pytest.fail(f"Phase 2 failed: {e}\nContent: {content_p2}")

    assert decision.should_alert is True
    assert decision.severity == "critical"

    prompt_phase3 = f"""
    You are Phase 3: NARRATIVE GENERATION

    Decision from Phase 2:
    - should_alert: {decision.should_alert}
    - severity: {decision.severity}
    - primary_signal: {decision.primary_signal}

    Data numbers: runway_days={runway_days:.0f}, burn={financial_data['burn_rate']}, balance={financial_data['bank_balance']}

    PRD Requirements:
    - pattern_name: Name only (e.g., "runway_compression")
    - insight: Max 200 words, include numbers: {runway_days:.0f} days, ${financial_data['burn_rate']:,}
    - urgency_horizon: "today" (critical)
    - one_action: ONE action only
    - injected_numbers: ["110", "60000", "220000"]

    Output JSON:
    {{
        "pattern_name": "...",
        "insight": "...",
        "urgency_horizon": "...",
        "one_action": "...",
        "injected_numbers": [...]
    }}

    Respond ONLY with valid JSON.
    """

    content_p3 = call_llm(ollama_client, llm_model, prompt_phase3, max_tokens=300)
    print(f"\n[Phase 3 - LLM Narrative Generation]\n{content_p3}")

    try:
        message = GuardianMessage(**parse_json_response(content_p3))
    except ValidationError as e:
        pytest.fail(f"Phase 3 failed: {e}\nContent: {content_p3}")

    assert len(message.insight.split()) <= 200, "insight > 200 words"
    assert not message.pattern_name.startswith("FG-"), "pattern_name should be name, not ID"

    print(f"\n[Full Flow Complete]")
    print(f"  Phase 1: {len(detected_patterns)} patterns detected (pure Python)")
    print(f"  Phase 2: decision={decision.should_alert}, severity={decision.severity}")
    print(f"  Phase 3: pattern={message.pattern_name}, words={len(message.insight.split())}")


# ============================================================================
# Test 5: Multi-Pattern Detection - Verify LLM handles complex scenarios
# ============================================================================

@pytest.mark.agentic
def test_llm_handles_multiple_anomalies(ollama_client, llm_model):
    """
    Test LLM can detect and prioritize multiple anomalies.

    Given a scenario with:
    - FG-01: Silent Churn (churn > 3%)
    - FG-04: Runway Compression (runway < 180)
    - FG-02: Burn Multiple Creep (burn > 2x ARR)

    LLM should identify all and correctly prioritize (critical > warning)
    """
    prompt = """
    You are a Finance Guardian analyzing a company with MULTIPLE anomalies.

    DATA:
    - MRR: $8,000
    - Net Burn: $25,000/month
    - Net New ARR: $5,000/month
    - Bank Balance: $80,000
    - Monthly Churn: 4%

    RULES (from watchlist):
    - FG-01: If monthly_churn_pct > 3% → WARNING
    - FG-02: If burn_multiple > 2.0 → CRITICAL (burn_multiple = burn / new_arr)
    - FG-04: If runway_days < 180 → CRITICAL (runway = balance / burn * 30)

    Compute and detect:
    - burn_multiple = 25000 / 5000 = 5.0 (CRITICAL)
    - runway_days = 80000 / 25000 * 30 = 96 days (CRITICAL)
    - churn_pct = 4% (WARNING)

    Output JSON with:
    {
        "anomalies": ["list of all FG-## detected"],
        "critical_count": number,
        "warning_count": number,
        "highest_priority": "critical"|"warning",
        "recommendation": "what to do first"
    }

    Respond ONLY with valid JSON.
    """

    content = call_llm(ollama_client, llm_model, prompt, max_tokens=400)
    print(f"\n[Multi-Anomaly Response]\n{content}")

    result = parse_json_response(content)

    assert len(result.get("anomalies", [])) >= 2, \
        f"Should detect at least 2 anomalies, got {result.get('anomalies')}"

    assert result.get("critical_count", 0) >= 2, \
        f"Should have at least 2 critical (FG-02, FG-04), got {result.get('critical_count')}"

    assert result.get("highest_priority") == "critical", \
        "Highest priority should be critical"


# ============================================================================
# Test 6: LLM Self-Correction - Verify LLM can correct invalid output
# ============================================================================

@pytest.mark.agentic
def test_llm_self_corrects_invalid_output(ollama_client, llm_model):
    """
    Test that LLM can self-correct when given feedback about invalid output.

    This simulates a production scenario where the LLM's initial output
    fails Pydantic validation, and we ask it to retry.
    """

    prompt_invalid = """
    Output JSON with this INVALID structure (missing required fields):
    {
        "pattern": "some_pattern"  # wrong field name, should be pattern_name
    }

    This is a test. Return exactly this malformed JSON.
    """

    initial_content = call_llm(ollama_client, llm_model, prompt_invalid, max_tokens=200)
    print(f"\n[Initial (Invalid) Response]\n{initial_content}")

    prompt_correction = f"""
    The previous output was invalid. The error was: "Missing field 'pattern_name'"

    Previous output:
    {initial_content}

    Now output VALID GuardianMessage JSON with ALL required fields:
    {{
        "pattern_name": "runway_compression",
        "insight": "Runway is critically low at 96 days. Burn multiple is 5.0x.",
        "urgency_horizon": "today",
        "one_action": "Freeze all non-essential spend immediately",
        "injected_numbers": ["96", "5", "80"]
    }}

    Respond ONLY with valid JSON that passes Pydantic validation.
    """

    corrected_content = call_llm(ollama_client, llm_model, prompt_correction, max_tokens=300)
    print(f"\n[Corrected Response]\n{corrected_content}")

    try:
        message = GuardianMessage(**parse_json_response(corrected_content))
    except ValidationError as e:
        pytest.fail(f"LLM failed to self-correct: {e}\nContent: {corrected_content}")

    assert message.pattern_name == "runway_compression"
    assert len(message.injected_numbers) > 0
    print("\n[Self-Correction Test Passed]")