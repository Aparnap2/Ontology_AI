"""
WeeklyCheckin — Monday 9am personalized briefing.
Uses GraphMemoryAgent to get momentum score.
"""
from __future__ import annotations
from dataclasses import dataclass
from src.config.llm import get_llm_client, get_chat_model

MESSAGES = {
    "after_win": {
        "en": "Good morning! Last week was your strongest in 6 weeks. How does it feel? Want to talk about what made it work?",
        "hi": "सुप्रभात! पिछला हफ्ता 6 हफ्तों में सबसे अच्छा रहा। कैसा लग रहा है?",
    },
    "after_tough": {
        "en": "Morning. Last week looked challenging from the numbers. How are you feeling about it?",
        "hi": "सुप्रभात। पिछला हफ्ता मुश्किल लगा। आप कैसा महसूस कर रहे हैं?",
    },
    "neutral": {
        "en": "Good morning! 🌅 How did last week go? Did things go the way you hoped?",
        "hi": "सुप्रभात! 🌅 पिछला हफ्ता कैसा रहा?",
    },
}

@dataclass
class CheckinMessage:
    text: str
    momentum: float
    mood: str  # after_win | after_tough | neutral

class WeeklyCheckin:
    def __init__(self, memory_agent, tone_filter=None) -> None:
        self._memory = memory_agent
        self._tone = tone_filter
        self._client = get_llm_client()
        self._model = get_chat_model()

    def get_message(self, founder_id: str, language: str = "en") -> CheckinMessage:
        patterns = self._memory.detect_patterns(founder_id)
        momentum = patterns.get("momentum_score", 0.5)

        if momentum > 0.70:
            mood = "after_win"
        elif momentum < 0.35:
            mood = "after_tough"
        else:
            mood = "neutral"

        lang_key = language if language in ("en", "hi") else "en"
        text = MESSAGES[mood].get(lang_key, MESSAGES[mood]["en"])

        return CheckinMessage(text=text, momentum=momentum, mood=mood)

    def generate_personalized_briefing(
        self,
        founder_id: str,
        language: str = "en",
    ) -> str:
        """Generate full weekly briefing using LLM + memory context."""
        patterns = self._memory.detect_patterns(founder_id)
        
        prompt = f"""You are OntologyAI, the Chief of Staff. Generate a weekly briefing.

Founder context:
- Archetype: {patterns.get('archetype', 'unknown')}
- Momentum: {patterns.get('momentum_score', 0.5):.2f}
- Commitment rate: {patterns.get('commitment_completion_rate', 0.5):.2f}
- Top patterns: {patterns.get('patterns', [])}

Rules:
- Max 4 sentences
- Lead with the most important thing
- End with ONE question or action
- Warm, direct, no jargon
- Language: {language}

Return JSON: {{"briefing": str, "one_action": str}}"""

        response = self._client.post(
            "/chat/completions",
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
        )
        response.raise_for_status()
        data = response.json()

        import json
        raw = data["choices"][0]["message"]["content"].strip()
        try:
            parsed = json.loads(raw)
            result = parsed.get("briefing", parsed.get("content", raw))
        except json.JSONDecodeError:
            result = raw
        return result
