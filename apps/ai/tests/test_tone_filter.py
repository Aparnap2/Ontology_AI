"""Tests for ToneFilter — mechanical tests run against real code, LLM tests run against real Ollama Cloud."""
import os
import sys

os.environ.setdefault("OLLAMA_BASE_URL", "https://ollama.com")
os.environ.setdefault("OLLAMA_API_KEY", os.environ.get("OLLAMA_API_KEY", ""))

from dotenv import load_dotenv
load_dotenv()

import pytest
from src.services.tone_filter import ToneFilter, ToneResult


# ── Jargon replacement (mechanical — pure code, no LLM) ──────────


@pytest.mark.parametrize(
    "jargon,should_be_gone",
    [
        ("EBITDA", "operating profit"),
        ("DSO", "days customers take to pay you"),
        ("basis points", "percentage points"),
        ("burn rate", "how fast you spend money"),
        ("runway", "months until cash runs out"),
        ("working capital", "money available day-to-day"),
        ("YoY", "vs last year"),
        ("MoM", "vs last month"),
        ("net margin", "profit kept from every ₹100 earned"),
        ("liquidity", "cash available right now"),
    ],
)
def test_jargon_replaced_mechanically(jargon, should_be_gone):
    """Jargon → plain English, zero LLM cost, always deterministic."""
    tf = ToneFilter()
    result = tf.apply(f"Check your {jargon}.", llm_rewrite=False)
    assert should_be_gone in result.text.lower() or jargon not in result.text
    assert result.jargon_replaced >= 1


def test_multiple_jargon_replaced():
    """Multiple jargon terms in one message."""
    tf = ToneFilter()
    result = tf.apply("Your EBITDA and DSO are both bad.", llm_rewrite=False)
    assert result.jargon_replaced >= 2


def test_no_jargon_unchanged():
    """No jargon → jargon_replaced = 0."""
    tf = ToneFilter()
    result = tf.apply("Revenue is up this month.", llm_rewrite=False)
    assert result.jargon_replaced == 0


# ── ToneResult structure ──────────────────────────────────────────


def test_apply_returns_tone_result():
    """apply() returns ToneResult dataclass."""
    tf = ToneFilter()
    result = tf.apply("Revenue fell.", llm_rewrite=False)
    assert isinstance(result, ToneResult)
    assert result.text
    assert result.language == "en"
    assert result.original == "Revenue fell."


def test_tone_result_has_jargon_count():
    """ToneResult.jargon_replaced counts mechanical replacements."""
    tf = ToneFilter()
    result = tf.apply("Check your EBITDA and DSO carefully.", llm_rewrite=False)
    assert result.jargon_replaced == 2


def test_tone_result_language_stored():
    """ToneResult.language reflects requested language."""
    tf = ToneFilter()
    result = tf.apply("Some text.", language="hi", llm_rewrite=False)
    assert result.language == "hi"


# ── LLM-powered tone rewrite (real Ollama Cloud) ────────────────────


@pytest.mark.slow
def test_tone_rewrite_replaces_ebitda():
    """LLM tone rewrite + mechanical jargon removal: EBITDA is gone."""
    tf = ToneFilter()
    result = tf.apply("Your EBITDA dropped this month.")
    assert "EBITDA" not in result.text
    assert result.jargon_replaced >= 1


@pytest.mark.slow
def test_good_news_tone_is_celebratory():
    """LLM rewrite with is_good_news=True produces warm output."""
    tf = ToneFilter()
    result = tf.apply("Revenue grew 20% this month.", is_good_news=True)
    assert result.text


@pytest.mark.slow
def test_bad_news_tone_is_calm():
    """LLM rewrite with is_good_news=False produces calm output."""
    tf = ToneFilter()
    result = tf.apply("Revenue dropped this month.", is_good_news=False)
    assert result.text


@pytest.mark.slow
def test_hindi_output_contains_devanagari():
    """Hindi translation produces Devanagari script."""
    tf = ToneFilter()
    result = tf.apply("Revenue is up this month.", language="hi")
    has_devanagari = any("\u0900" <= char <= "\u097F" for char in result.text)
    assert has_devanagari, f"Hindi output must contain Devanagari script: {result.text[:50]}"


@pytest.mark.slow
def test_apply_text_convenience_method():
    """apply_text() returns just the string, not ToneResult."""
    tf = ToneFilter()
    text = tf.apply_text("EBITDA is down.")
    assert isinstance(text, str)
    assert "EBITDA" not in text


# ── Client contract (regression — no network) ─────────────────────
# ToneFilter.__init__ wires get_llm_client(), which returns an
# openai.OpenAI client. The chat call must go through the SDK
# (chat.completions.create); the old httpx-style
# self._client.post("/chat/completions", json=...) raised
# TypeError: SyncAPIClient.post() got an unexpected keyword argument 'json'.


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [type("_C", (), {"message": type("_M", (), {"content": content})()})()]


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[dict] = []

    def create(self, **kwargs) -> _FakeResponse:
        self.calls.append(kwargs)
        return _FakeResponse(self._content)


class _FakeClient:
    """Stand-in for openai.OpenAI exposing only chat.completions.create.

    Deliberately has no ``post`` attribute: any regression back to the
    httpx-style call raises AttributeError and fails the test.
    """

    def __init__(self, content: str) -> None:
        self.completions = _FakeCompletions(content)
        self.chat = type("_Chat", (), {"completions": self.completions})()


def _install_fake_client(monkeypatch, content: str) -> _FakeClient:
    fake = _FakeClient(content)
    monkeypatch.setattr("src.services.tone_filter.get_llm_client", lambda: fake)
    return fake


def test_tone_rewrite_calls_openai_chat_completions(monkeypatch):
    """Tone rewrite must use the OpenAI SDK, not httpx .post(json=)."""
    fake = _install_fake_client(monkeypatch, "You keep less from each sale.")
    result = ToneFilter().apply("Your EBITDA dropped this month.")

    assert result.text == "You keep less from each sale."
    assert len(fake.completions.calls) == 1
    call = fake.completions.calls[0]
    assert call["messages"][0]["role"] == "system"
    assert "model" in call
    assert "temperature" in call


def test_translate_hindi_calls_openai_chat_completions(monkeypatch):
    """Hindi path uses chat.completions.create for both rewrite and translate."""
    fake = _install_fake_client(monkeypatch, "आपकी बिक्री बढ़ी है।")
    result = ToneFilter().apply("Revenue is up this month.", language="hi")

    assert result.text == "आपकी बिक्री बढ़ी है।"
    assert result.language == "hi"
    assert len(fake.completions.calls) == 2