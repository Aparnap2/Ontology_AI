"""
DSPy signatures for the AnomalyAgent.

Uses Ollama qwen3:0.6b via the OpenAI-compatible endpoint.
"""
from __future__ import annotations
import os
import dspy

# ── Configure DSPy LM (Ollama, OpenAI-compat endpoint) ───────────
_OLLAMA_BASE  = os.getenv("OLLAMA_BASE_URL",   "http://localhost:11434/v1")
_CHAT_MODEL   = os.getenv("OLLAMA_CHAT_MODEL", "qwen3:0.6b")

_lm = dspy.LM(
    model=f"openai/{_CHAT_MODEL}",
    api_base=_OLLAMA_BASE,
    api_key="ollama",
    temperature=0.2,
    max_tokens=512,
    cache=False,
)
dspy.configure(lm=_lm)


# ── Signature 1: AnomalyExplainer (reused from PulseAgent) ───────

class AnomalyExplainer(dspy.Signature):
    """
    You are Sarthi. A metric has moved unexpectedly.
    Explain what it means to the founder in plain English.
    Be specific: reference the numbers. Suggest one thing to check first.
    """
    metric_name:      str = dspy.InputField(desc="Name of the anomalous metric")
    current_value:    str = dspy.InputField(desc="Current metric value")
    baseline_value:   str = dspy.InputField(desc="Expected / baseline value")
    deviation_pct:    str = dspy.InputField(desc="% deviation from baseline")
    historical:       str = dspy.InputField(
                          desc="Relevant historical context for this metric")

    explanation:      str = dspy.OutputField(
                          desc="Plain-English explanation of what changed and why it matters")
    check_first:      str = dspy.OutputField(
                          desc="The single most important thing to investigate first")


# ── Signature 2: AnomalyActionGenerator ──────────────────────────

class AnomalyActionGenerator(dspy.Signature):
    """
    You are Sarthi. Given an anomaly explanation, generate ONE concrete
    action for the founder to take. Not advice. An action.
    """
    explanation:      str = dspy.InputField(desc="Explanation of the anomaly")
    metric_name:      str = dspy.InputField(desc="Name of the anomalous metric")
    current_value:    str = dspy.InputField(desc="Current metric value")

    action_item:      str = dspy.OutputField(
                          desc="One concrete action starting with a verb, max 15 words")


# ── Instantiated predictors ──────────────────────────────────────
anomaly_explainer       = dspy.Predict(AnomalyExplainer)
anomaly_action_generator = dspy.Predict(AnomalyActionGenerator)


# ── Signature 3: GuardianInsight ─────────────────────────────────

class GuardianInsight(dspy.Signature):
    """
    You are a guardian who has seen dozens of seed-stage startups fail.
    You have just detected a pattern the founder hasn't noticed.
    You are NOT an assistant returning data. You are telling them
    something they need to know BEFORE it becomes a crisis.

    Rules (non-negotiable):
    - Start with the PATTERN NAME, never a number
    - Numbers are evidence. The pattern is the insight.
    - Give the urgency horizon specific to their fundraise timeline
    - Reference what typically happens to founders who miss this
    - End with ONE concrete action this week
    - Max 200 words
    - Sound like a trusted colleague. Never a dashboard notification.
    - Never use: "consider monitoring", "you may want to",
      "it seems like", "great job". You are a guardian, not a chatbot.
    """
    context:              str = dspy.InputField(
                              desc="Prior events and patterns from memory. "
                                   "Example: 'Churn was 2.8% last month, now 3.4%'")
    blindspot_name:       str = dspy.InputField(
                              desc="Pattern name. Example: 'Silent Churn Death'")
    why_it_matters:       str = dspy.InputField(
                              desc="Why this matters at seed stage.")
    what_founder_doesnt_know: str = dspy.InputField(
                              desc="What the founder is missing.")
    urgency_horizon:      str = dspy.InputField(
                              desc="Timeline specific to fundraise. "
                                   "Example: '~8 months before Series A'")
    historical_precedent: str = dspy.InputField(
                              desc="What typically happened to others.")
    one_action:           str = dspy.InputField(
                              desc="One concrete action this week.")
    current_metric:       str = dspy.InputField(
                              desc="Exact metric values. Example: '3.4% monthly churn'")
    implied_at_scale:     str = dspy.InputField(
                              desc="What this means annually/at Series A. "
                                   "Example: '36% annual churn'")
    guardian_message:     str = dspy.OutputField(
                              desc="Guardian insight. Pattern first. Action last. "
                                   "200 words max. Prose only. "
                                   "Reads like a message from someone who has "
                                   "been through this before.")


guardian_insight = dspy.Predict(GuardianInsight)
