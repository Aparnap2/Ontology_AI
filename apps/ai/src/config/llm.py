"""LLM client factory for Sarthi v4.2 — Groq (primary) or OpenRouter (fallback)."""
from __future__ import annotations

import os
from typing import Any

from src.llmops.tracer import trace_chat_completion

import httpx

_client: httpx.Client | None = None


def _groq_configured() -> bool:
    return bool(os.environ.get("GROQ_API_KEY", ""))


def _provider_config() -> tuple[str, str]:
    """Return (base_url, api_key) for the active LLM provider."""
    if _groq_configured():
        return (
            os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            os.environ["GROQ_API_KEY"],
        )
    return (
        os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        os.environ.get("OPENROUTER_API_KEY", ""),
    )


def get_llm_client() -> httpx.Client:
    """Returns OpenAI-compatible httpx Client singleton."""
    global _client
    if _client is None:
        base_url, api_key = _provider_config()
        _client = httpx.Client(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
    return _client


def get_chat_model() -> str:
    """Returns default chat model for the active provider."""
    if _groq_configured():
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


@trace_chat_completion
def chat_completion(
    messages: list[dict[str, str]],
    model: str | None = None,
    max_tokens: int = 500,
    temperature: float = 0.0,
    json_mode: bool = False,
    **extra: Any,
) -> str:
    """POST /chat/completions and return assistant content."""
    payload: dict[str, Any] = {
        "model": model or get_chat_model(),
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        **extra,
    }
    if _groq_configured():
        payload.setdefault("reasoning_effort", os.environ.get("GROQ_REASONING_EFFORT", "none"))
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    response = get_llm_client().post("/chat/completions", json=payload)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


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
    """Reset cached client."""
    global _client
    if _client:
        _client.close()
    _client = None


get_model = get_chat_model
