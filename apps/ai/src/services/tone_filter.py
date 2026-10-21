"""
ToneFilter — mandatory output wrapper for every agent.
No agent output reaches a founder without passing through here.
Enforced at the Temporal activity boundary in activities.go.
"""
from __future__ import annotations
import os
import re
import json
import httpx
from dataclasses import dataclass
from src.config.llm import get_llm_client, get_chat_model

_openrouter_client: httpx.Client | None = None


def _get_openrouter_client() -> httpx.Client:
    global _openrouter_client
    if _openrouter_client is None:
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        _openrouter_client = httpx.Client(base_url=base_url, headers=headers, timeout=60.0)
    return _openrouter_client

# ── Mechanical replacements (no LLM cost) ─────────────────────────────
JARGON_MAP: dict[str, str] = {
    r"\bEBITDA\b":               "operating profit",
    r"\bbasis points?\b":        "percentage points",
    r"\bDSO\b":                  "days customers take to pay you",
    r"\baccounts receivable\b":  "money customers owe you",
    r"\baccounts payable\b":     "money you owe suppliers",
    r"\bcash conversion cycle\b":"how long your money is tied up",
    r"\bworking capital\b":      "money available day-to-day",
    r"\bliquidity\b":            "cash available right now",
    r"\bnet margin\b":           "profit kept from every ₹100 earned",
    r"\bgross margin\b":         "profit after direct costs",
    r"\bYoY\b":                  "vs last year",
    r"\bMoM\b":                  "vs last month",
    r"\bQoQ\b":                  "vs last quarter",
    r"\bdebt.to.equity\b":       "how much you owe vs how much you own",
    r"\bburn rate\b":            "how fast you spend money",
    r"\brunway\b":               "months until cash runs out",
    r"\breconcil\w*\b":          "check records match reality",
    r"\bamortiz\w*\b":           "spread the cost over time",
    r"\bdepreciation\b":         "drop in value over time",
    r"\breceivables\b":          "money owed to you",
    r"\bpayables\b":             "money you owe",
    r"\bP&L\b":                  "profit and loss summary",
    r"\bbalance sheet\b":        "snapshot of what you own and owe",
    r"\boptimize\b":             "improve",
    r"\bleverage\b":             "use",
    r"\bsynerg\w*\b":            "combined benefit",
    r"\bstreamline\b":           "simplify",
    r"\bactionable insights?\b": "things to do",
    r"\bKPIs?\b":                "key numbers",
    r"\bbps\b":                  "%",
    r"\brun rate\b":             "current pace",
    r"\bunit economics\b":       "profit per customer",
    r"\bCAC\b":                  "cost to get a customer",
    r"\bLTV\b":                  "lifetime value per customer",
    r"\bchurn\b":                "customers you're losing",
    r"\bMRR\b":                  "monthly recurring revenue",
    r"\bARR\b":                  "annual recurring revenue",
    r"\bGMV\b":                  "total sales volume",
}

TONE_SYSTEM_PROMPT = """\
Rewrite this message so it sounds like a trusted, warm, knowledgeable
friend — not a financial consultant or software tool.

RULES (every one is mandatory):
1. No jargon. Replace any financial term with plain language.
2. Lead with the human reality, not the metric.
   WRONG: "Your margin compressed 340bps"
   RIGHT:  "You're keeping less from each sale than last month"
3. Use specific ₹ amounts, not percentages alone.
4. End with exactly ONE question OR one concrete action — never a list.
5. If good news: celebrate it genuinely first, then give the insight.
6. If bad news: open with warmth and calm ("let's look at this together"),
   never with alarm.
7. Never use: optimize, leverage, synergy, streamline, actionable,
   insights, data-driven.
8. Maximum 4 sentences for a proactive alert.
   Longer is allowed only if the founder asked a direct question.
9. Never make the founder feel stupid for not knowing something.
10. Tone: warm, direct, specific — like a friend who happens to be
    a financial expert and cares about this business personally.\
"""

HINDI_SYSTEM_PROMPT = """\
Translate to conversational Hindi that a small business owner in
India would use with a trusted friend.
- NOT formal/bureaucratic Hindi
- Use Devanagari script
- Keep ₹ symbol and all numbers as digits
- Preserve any English product names or brand names
- Match the warmth and directness of the original\
"""


@dataclass
class ToneResult:
    text: str
    language: str
    jargon_replaced: int  # count of mechanical replacements made
    original: str  # original input message


class ToneFilter:
    """
    Wraps every agent output before delivery to a founder.
    Two-stage: mechanical jargon kill → LLM tone rewrite.
    Optional Hindi translation as a third stage.
    """

    def __init__(self) -> None:
        self._client = get_llm_client()
        self._model = get_chat_model()

    # ── Public API ─────────────────────────────────────────────────────

    def apply(
        self,
        raw_message: str,
        context_type: str = "proactive",
        # "proactive" | "diagnostic" | "decision" | "celebration"
        is_good_news: bool = False,
        owner_name: str | None = None,
        language: str = "en",
        llm_rewrite: bool = True,
    ) -> ToneResult:
        """
        Main entry point. Called by every Temporal activity
        before SendSlackActivity or SendWhatsAppActivity.

        Args:
            llm_rewrite: If False, skip LLM call and return mechanical
                jargon-replaced text only. Useful for fast tests.
        """
        cleaned, n_replaced = self._kill_jargon(raw_message)

        if llm_rewrite:
            rewritten = self._tone_rewrite(
                cleaned, context_type, is_good_news, owner_name
            )
            if language == "hi":
                rewritten = self._translate_hindi(rewritten)
        else:
            rewritten = cleaned

        return ToneResult(
            text=rewritten,
            language=language,
            jargon_replaced=n_replaced,
            original=raw_message,
        )

    def apply_text(self, raw: str, **kwargs) -> str:
        """Convenience method returning just the string."""
        return self.apply(raw, **kwargs).text

    # ── Private ────────────────────────────────────────────────────────

    def _kill_jargon(self, text: str) -> tuple[str, int]:
        count = 0
        for pattern, replacement in JARGON_MAP.items():
            new_text, n = re.subn(pattern, replacement, text, flags=re.IGNORECASE)
            count += n
            text = new_text
        return text, count

    def _tone_rewrite(
        self,
        message: str,
        context_type: str,
        is_good_news: bool,
        owner_name: str | None,
    ) -> str:
        mood = (
            "This is GOOD NEWS — lead with genuine celebration."
            if is_good_news
            else "This may be concerning — open with warmth and calm."
        )
        name_hint = (
            f"Address them as {owner_name} where it feels natural."
            if owner_name
            else ""
        )
        user_content = (
            f"Context type: {context_type}\n"
            f"{mood}\n"
            f"{name_hint}\n\n"
            f"Rewrite this message:\n\n{message}"
        )
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": TONE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.25,
        )
        raw = response.choices[0].message.content.strip()
        try:
            parsed = json.loads(raw)
            text = parsed.get("text", parsed.get("rewritten", raw))
        except json.JSONDecodeError:
            text = raw
        return text

    def _translate_hindi(self, text: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": HINDI_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.15,
        )
        return response.choices[0].message.content.strip()
