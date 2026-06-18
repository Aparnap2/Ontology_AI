"""LLM client factory for TrackGuard v4.2 — single source of truth using OpenAI SDK.

Providers: Groq (primary), OpenAI, OpenRouter.
All LLM calls MUST go through this module. No direct client instantiation elsewhere.

Observability: Every call logs token usage, latency, and estimated cost.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from collections.abc import Generator, AsyncGenerator

from openai import OpenAI, AsyncOpenAI

from src.llmops.tracer import trace_chat_completion
from src.llmops.call_log import log_llm_call

_client: OpenAI | None = None
_async_client: AsyncOpenAI | None = None


# ═══════════════════════════════════════════════════════════════════
# Observability: LLMCallResult, pricing, cost estimation
# ═══════════════════════════════════════════════════════════════════


@dataclass
class LLMCallResult:
    """Result of an LLM call with observability metadata.

    Wraps the raw response content with token counts, latency, and cost.
    Use ``chat_completion_with_metrics()`` to obtain an instance.
    """
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    cached_tokens: int = 0
    finish_reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# Pricing per 1M tokens — update as providers adjust rates
_MODEL_PRICING: dict[str, dict[str, float]] = {
    "qwen/qwen3-32b": {"input": 0.0, "output": 0.0},             # Groq free tier
    "llama-3.3-70b-versatile": {"input": 0.0, "output": 0.0},     # Groq free tier
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
}


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate cost in USD based on model pricing.

    Falls back to zero-cost for unknown models (prevents false alerts).
    """
    pricing = _MODEL_PRICING.get(model, {"input": 0.0, "output": 0.0})
    return (prompt_tokens * pricing["input"] + completion_tokens * pricing["output"]) / 1_000_000


def _extract_usage(response: Any) -> tuple[int, int, int, int]:
    """Extract token usage from an OpenAI ChatCompletion response.

    Returns (prompt_tokens, completion_tokens, total_tokens, cached_tokens).
    Handles mock responses and real SDK responses gracefully.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return (0, 0, 0, 0)
    prompt = getattr(usage, "prompt_tokens", 0) or 0
    completion = getattr(usage, "completion_tokens", 0) or 0
    total = getattr(usage, "total_tokens", 0) or 0
    cached = getattr(usage, "prompt_tokens_details", None)
    cached_count = getattr(cached, "cached_tokens", 0) if cached else 0
    return (prompt, completion, total, cached_count or 0)


# ═══════════════════════════════════════════════════════════════════
# Provider configuration
# ═══════════════════════════════════════════════════════════════════


def _provider_config() -> tuple[str, str]:
    """Return (base_url, api_key) for the active LLM provider.

    Provider priority: GROQ_API_KEY → OPENROUTER_API_KEY → OPENAI_API_KEY.
    Each provider reads: {PROVIDER}_API_KEY, {PROVIDER}_BASE_URL.
    """
    if os.environ.get("GROQ_API_KEY"):
        return (
            os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            os.environ["GROQ_API_KEY"],
        )
    if os.environ.get("OPENROUTER_API_KEY"):
        return (
            os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            os.environ["OPENROUTER_API_KEY"],
        )
    return (
        os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        os.environ.get("OPENAI_API_KEY", ""),
    )


def _is_groq() -> bool:
    """Check if the active provider is Groq."""
    return bool(os.environ.get("GROQ_API_KEY"))


def get_llm_client() -> OpenAI:
    """Returns OpenAI-compatible client singleton.

    Reads provider config from env vars at creation time.
    Call reset_client() to recreate with updated env vars.
    """
    global _client
    if _client is None:
        base_url, api_key = _provider_config()
        _client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=60.0,
        )
    return _client


def get_chat_model() -> str:
    """Returns default chat model for the active provider.

    Env var priority: {PROVIDER}_CHAT_MODEL → LLM_MODEL → provider default.
    """
    if _is_groq():
        return os.environ.get(
            "GROQ_CHAT_MODEL",
            os.environ.get("LLM_MODEL", "qwen/qwen3-32b"),
        )
    return os.environ.get(
        "OPENROUTER_LLM_MODEL",
        "nvidia/nemotron-3-super-120b-a12b:free",
    )


def get_embedding_model() -> str:
    """Returns default embedding model (OpenRouter)."""
    return os.environ.get(
        "OPENROUTER_EMBED_MODEL",
        "nvidia/llama-nemotron-embed-vl-1b-v2:free",
    )


# ═══════════════════════════════════════════════════════════════════
# Core chat completion functions
# ═══════════════════════════════════════════════════════════════════


def _build_kwargs(
    messages: list[dict[str, str]],
    model: str | None = None,
    max_tokens: int = 500,
    temperature: float = 0.0,
    json_mode: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    """Build kwargs dict for chat completion requests."""
    kwargs: dict[str, Any] = {
        "model": model or get_chat_model(),
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        **extra,
    }
    if _is_groq():
        kwargs.setdefault(
            "reasoning_effort",
            os.environ.get("GROQ_REASONING_EFFORT", "none"),
        )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    return kwargs


def _extract_finish_reason(response: Any) -> str:
    """Extract finish_reason from first choice, safely."""
    choices = getattr(response, "choices", None)
    if not choices:
        return ""
    first = choices[0]
    return getattr(first, "finish_reason", "") or ""


@trace_chat_completion
def chat_completion(
    messages: list[dict[str, str]],
    model: str | None = None,
    max_tokens: int = 500,
    temperature: float = 0.0,
    json_mode: bool = False,
    **extra: Any,
) -> str:
    """POST /chat/completions and return assistant content.

    Uses OpenAI SDK client.chat.completions.create() under the hood.
    Supports json_mode via response_format and reasoning_effort for Groq.

    This function is backward-compatible — returns plain text string.
    For observability metadata (tokens, cost, latency), use
    ``chat_completion_with_metrics()`` instead.
    """
    kwargs = _build_kwargs(messages, model, max_tokens, temperature, json_mode, **extra)

    t0 = time.monotonic()
    try:
        response = get_llm_client().chat.completions.create(**kwargs)
    except Exception:
        latency_ms = (time.monotonic() - t0) * 1000
        log_llm_call(
            model=kwargs["model"],
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=latency_ms,
            cost_usd=0.0,
            operation="chat_completion",
            success=False,
            error="call_failed",
        )
        raise

    latency_ms = (time.monotonic() - t0) * 1000
    prompt_t, comp_t, total_t, cached_t = _extract_usage(response)
    cost = _estimate_cost(kwargs["model"], prompt_t, comp_t)

    log_llm_call(
        model=kwargs["model"],
        prompt_tokens=prompt_t,
        completion_tokens=comp_t,
        total_tokens=total_t,
        latency_ms=latency_ms,
        cost_usd=cost,
        operation="chat_completion",
        success=True,
    )

    return response.choices[0].message.content.strip()


@trace_chat_completion
def chat_completion_with_metrics(
    messages: list[dict[str, str]],
    model: str | None = None,
    max_tokens: int = 500,
    temperature: float = 0.0,
    json_mode: bool = False,
    **extra: Any,
) -> LLMCallResult:
    """POST /chat/completions and return ``LLMCallResult`` with full metrics.

    Identical to ``chat_completion()`` but returns an ``LLMCallResult``
    dataclass containing token counts, latency, and estimated cost.
    The structured call log is also emitted automatically.
    """
    kwargs = _build_kwargs(messages, model, max_tokens, temperature, json_mode, **extra)

    t0 = time.monotonic()
    try:
        response = get_llm_client().chat.completions.create(**kwargs)
    except Exception:
        latency_ms = (time.monotonic() - t0) * 1000
        log_llm_call(
            model=kwargs["model"],
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=latency_ms,
            cost_usd=0.0,
            operation="chat_completion_with_metrics",
            success=False,
            error="call_failed",
        )
        raise

    latency_ms = (time.monotonic() - t0) * 1000
    prompt_t, comp_t, total_t, cached_t = _extract_usage(response)
    cost = _estimate_cost(kwargs["model"], prompt_t, comp_t)

    log_llm_call(
        model=kwargs["model"],
        prompt_tokens=prompt_t,
        completion_tokens=comp_t,
        total_tokens=total_t,
        latency_ms=latency_ms,
        cost_usd=cost,
        operation="chat_completion_with_metrics",
        success=True,
    )

    return LLMCallResult(
        content=response.choices[0].message.content.strip(),
        model=kwargs["model"],
        prompt_tokens=prompt_t,
        completion_tokens=comp_t,
        total_tokens=total_t,
        latency_ms=latency_ms,
        cost_usd=cost,
        cached_tokens=cached_t,
        finish_reason=_extract_finish_reason(response),
    )


def chat_completion_stream(
    messages: list[dict[str, str]],
    model: str | None = None,
    max_tokens: int = 500,
    temperature: float = 0.0,
    json_mode: bool = False,
    **extra: Any,
) -> Generator[str, None, None]:
    """Stream chat completion chunks as they arrive.

    Yields content delta strings. Use for real-time UI updates or
    token-by-token processing. For full response, use chat_completion().

    Usage:
        for chunk in chat_completion_stream(messages=[...]):
            print(chunk, end="", flush=True)
    """
    kwargs = _build_kwargs(messages, model, max_tokens, temperature, json_mode, **extra)
    stream = get_llm_client().chat.completions.create(**kwargs, stream=True)
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


async def chat_completion_stream_async(
    messages: list[dict[str, str]],
    model: str | None = None,
    max_tokens: int = 500,
    temperature: float = 0.0,
    json_mode: bool = False,
    **extra: Any,
) -> AsyncGenerator[str, None]:
    """Async stream chat completion chunks as they arrive.

    Yields content delta strings. Use for async UI updates or
    token-by-token processing in async contexts.

    Usage:
        async for chunk in chat_completion_stream_async(messages=[...]):
            print(chunk, end="", flush=True)
    """
    global _async_client
    if _async_client is None:
        base_url, api_key = _provider_config()
        _async_client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=60.0,
        )
    kwargs = _build_kwargs(messages, model, max_tokens, temperature, json_mode, **extra)
    async with _async_client.chat.completions.stream(**kwargs) as stream:
        async for event in stream:
            if event.type == "content.delta" and event.delta:
                yield event.delta


def strip_reasoning(content: str) -> str:
    """Remove Qwen3/Groq thinking blocks from model output."""
    text = content.strip()
    open_think = "<" + "think" + ">"
    close_think = "</" + "think" + ">"
    lowered = text.lower()
    while "<think>" in lowered:
        start = lowered.find("<think>")
        end = lowered.find("</think>", start)
        if end == -1:
            break
        text = text[:start] + text[end + len("</think>") :]
        lowered = text.lower()
    while open_think in lowered:
        start = lowered.find(open_think)
        end = lowered.find(close_think, start)
        if end == -1:
            break
        text = text[:start] + text[end + len(close_think) :]
        lowered = text.lower()
    return text.strip()


def extract_json_content(content: str) -> str:
    """Extract JSON object/array from LLM output."""
    import re

    text = strip_reasoning(content)
    if "```json" in text:
        return text.split("```json", 1)[1].split("```", 1)[0].strip()
    if "```" in text:
        return text.split("```", 1)[1].split("```", 1)[0].strip()
    match = re.search(r"(\{.*\}|\[.*\])", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def reset_client() -> None:
    """Reset cached clients."""
    global _client, _async_client
    if _client:
        _client.close()
    _client = None
    _async_client = None


get_model = get_chat_model
