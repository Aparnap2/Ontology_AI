"""LLM primitives for skills — all generation routes through src/config/llm.py.

Requirement #1: no direct client instantiation anywhere in ``src/mission/``.
Every call goes through ``chat_completion_with_metrics`` (which owns the
provider client, metrics, and structured call log). The module attribute
``llm_module`` is the seam tests monkeypatch.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src.config import llm as llm_module

logger = logging.getLogger(__name__)

# Primitive names declared on SkillDefinition.llm_calls — keep in sync with
# the functions below.
PRIMITIVES = (
    "summarize",
    "analyze_kpi",
    "compare_options",
    "generate_recommendation",
    "draft_message",
    "organizational_brief",
)


def _parse_json(content: str) -> dict[str, Any]:
    """Parse a JSON payload from an LLM response (fence-tolerant)."""
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        cleaned = llm_module.extract_json_content(content)
        return json.loads(cleaned)


def _chat(messages: list[dict[str, str]], *, max_tokens: int = 500, json_mode: bool = False):
    """Single seam into the config LLM layer."""
    return llm_module.chat_completion_with_metrics(
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.0,
        json_mode=json_mode,
    )


async def summarize(ctx: Any, content: str, *, max_tokens: int = 400) -> str:
    """Condense evidence/content into a short summary."""
    result = _chat(
        [
            {"role": "system", "content": "Summarize the following content concisely."},
            {"role": "user", "content": content},
        ],
        max_tokens=max_tokens,
    )
    return result.content


async def analyze_kpi(ctx: Any, evidence: list[dict[str, Any]], *, kpi: str) -> dict[str, Any]:
    """Analyze evidence against a KPI and return structured findings."""
    result = _chat(
        [
            {
                "role": "system",
                "content": (
                    f"You analyze business evidence against the KPI '{kpi}'. "
                    "Return JSON with keys: findings, trend, confidence."
                ),
            },
            {"role": "user", "content": json.dumps(evidence, default=str)},
        ],
        json_mode=True,
    )
    return _parse_json(result.content)


async def compare_options(
    ctx: Any, options: list[dict[str, Any]], criterion: str
) -> dict[str, Any]:
    """Compare options on a criterion and return a structured decision."""
    result = _chat(
        [
            {
                "role": "system",
                "content": (
                    f"Compare the options on the criterion '{criterion}'. "
                    "Return JSON with keys: selected, rationale, confidence, terminal."
                ),
            },
            {"role": "user", "content": json.dumps(options, default=str)},
        ],
        json_mode=True,
    )
    return _parse_json(result.content)


async def generate_recommendation(
    ctx: Any, analysis: dict[str, Any], *, max_tokens: int = 500
) -> dict[str, Any]:
    """Turn an analysis into a concrete recommendation."""
    result = _chat(
        [
            {
                "role": "system",
                "content": (
                    "Produce a concrete, actionable recommendation. "
                    "Return JSON with keys: action, owner, priority, rationale."
                ),
            },
            {"role": "user", "content": json.dumps(analysis, default=str)},
        ],
        max_tokens=max_tokens,
        json_mode=True,
    )
    return _parse_json(result.content)


async def draft_message(
    ctx: Any, intent: str, context: dict[str, Any], *, max_tokens: int = 300
) -> str:
    """Draft a human-ready message (Slack/email) for the given intent."""
    result = _chat(
        [
            {
                "role": "system",
                "content": (
                    f"Draft a concise, human message for the intent: {intent}. "
                    "Plain text only, no JSON."
                ),
            },
            {"role": "user", "content": json.dumps(context, default=str)},
        ],
        max_tokens=max_tokens,
    )
    return result.content


async def organizational_brief(
    ctx: Any, findings: dict[str, Any], *, max_tokens: int = 600
) -> str:
    """Compose an organizational brief from structured findings."""
    result = _chat(
        [
            {
                "role": "system",
                "content": (
                    "Compose a crisp organizational brief for the founder from the "
                    "findings. Plain text only, no JSON."
                ),
            },
            {"role": "user", "content": json.dumps(findings, default=str)},
        ],
        max_tokens=max_tokens,
    )
    return result.content