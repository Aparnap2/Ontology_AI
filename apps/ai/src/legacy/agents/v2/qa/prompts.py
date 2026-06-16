"""
DSPy signatures and ReAct agent prompts for the QAAgent.

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
    max_tokens=256,
    cache=False,
)
dspy.configure(lm=_lm)


# ── The 20 canonical founder questions ───────────────────────────

FOUNDER_QUESTIONS = {
    "mrr":             "What is our current MRR?",
    "arr":             "What is our ARR?",
    "mrr_growth":      "How did MRR grow this month?",
    "burn":            "What is our monthly burn?",
    "runway":          "How many months of runway do we have?",
    "balance":         "What is our bank balance?",
    "customers":       "How many paying customers do we have?",
    "new_customers":   "How many new customers did we add this month?",
    "churn":           "What is our churn rate?",
    "churned":         "How many customers churned this month?",
    "top_customers":   "Who are our top customers by revenue?",
    "cac":             "What is our CAC?",
    "ltv":             "What is our LTV?",
    "active_users":    "How many active users did we have last month?",
    "revenue_growth":  "What is our revenue growth rate?",
    "biggest_expense": "What is our biggest expense?",
    "vendor_costs":    "How much are we spending on AWS / infra?",
    "last_week":       "What happened to revenue last week?",
    "vs_last_month":   "How does this month compare to last month?",
    "investor_update": "Can you draft my investor update?",
}


# ── Tool descriptions for ReAct agent ────────────────────────────

TOOL_DESCRIPTIONS = {
    "search_pulse_memory": (
        "Search past business pulse snapshots for context. "
        "Use this to find historical answers or trends for a given question. "
        "Parameters: query (str) — the search query; tenant_id (str) — the tenant identifier. "
        "Returns: top 3 matching memory entries as a formatted string."
    ),
    "query_stripe_metrics": (
        "Get Stripe metrics for a tenant. "
        "Use this to retrieve MRR, ARR, churn, new customers, and other payment metrics. "
        "Parameters: metric (str) — one of 'mrr', 'arr', 'churn', 'new_customers', 'active_customers', 'churned_customers'; "
        "tenant_id (str) — the tenant identifier. "
        "Returns: formatted metric value with units."
    ),
    "query_product_db": (
        "Query product DB for usage metrics: DAU, MAU, retention, active users. "
        "Use this for product engagement questions, not revenue. "
        "Parameters: question (str) — the product question; tenant_id (str) — the tenant identifier. "
        "Returns: formatted product metrics result."
    ),
    "search_decisions": (
        "Search past business decisions from the decision journal. "
        "Use this when asked about past decisions or choices made. "
        "Parameters: query (str) — the search query; tenant_id (str) — the tenant identifier. "
        "Returns: top 3 matching decisions with context."
    ),
}


# ── ReAct agent system prompt ────────────────────────────────────

REACT_SYSTEM_PROMPT = (
    "You are TrackGuard, a proactive business co-founder AI. "
    "Answer the founder's question using ONLY their real data. "
    "Available data sources: PulseAgent metrics, Decision Journal history. "
    "When asked about past decisions, search the decisions collection first. "
    "Be direct. Lead with the number. Max 100 words. "
    "If the answer isn't in the data, say 'I don't have that data yet. "
    "Connect your Stripe/bank account to get this.'"
)


# ── Signature: FounderQA ─────────────────────────────────────────

class FounderQA(dspy.Signature):
    """
    Answer a SaaS founder's business question directly.
    Use the data provided. Be specific — use numbers.
    1-2 sentences max. No preamble. No buzzwords.
    If the answer isn't in the data, say 'I don't have that data yet.
    Connect your Stripe/bank account to get this.'
    """
    question:   str = dspy.InputField(desc="Founder's question")
    data:       str = dspy.InputField(desc="Current business metrics as JSON")
    past_answer:str = dspy.InputField(
                      desc="Previous answer to this question from memory, or 'First time asked.'")

    answer:     str = dspy.OutputField(
                      desc="Direct 1-2 sentence answer with numbers. End with one follow-up if relevant.")


# ── Instantiated predictor ──────────────────────────────────────
founder_qa = dspy.Predict(FounderQA)
