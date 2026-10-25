"""Shared, deterministic matching for evaluation gold criteria.

The evaluators run without an LLM. Criteria are matched by requiring the
meaningful concepts and numeric evidence named by each criterion, while
allowing the simulator's natural paraphrases. Optional criteria return
``None`` so callers can exclude them from score denominators.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

_NUMBER_RE = re.compile(
    r"(?<![\w.])(?P<number>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>%|x|k|m)?(?![a-z])",
    re.IGNORECASE,
)
_OPTIONAL_MARKERS = ("may ", "if in context", "if available")

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "available", "be", "by", "context",
    "for", "from", "if", "in", "is", "least", "may", "mention", "mentions",
    "name", "names", "number", "numbers", "of", "on", "or", "specific",
    "suggest", "suggests", "that", "the", "this", "to", "value", "values",
    "with",
}

_GENERIC_WITH_NUMBERS = {
    "amount", "amounts", "current", "decrease", "increase", "large", "multiple",
    "normal", "period", "ratio", "time",
}

_CONCEPTS = {
    "alarm": {"alarm", "alert", "panic", "emergency", "crisis"},
    "approval": {"approval", "approve", "approved", "authorization", "authorized"},
    "category": {"category", "categories"},
    "check": {"check", "checking", "verify", "verifying", "review", "reviewing", "audit", "inspect"},
    "decline": {"decline", "declining", "decrease", "decreased", "drop", "dropped", "down", "fell", "fall"},
    "duplicate": {"duplicate", "duplicated", "double", "identical", "twice"},
    "expected": {"expected", "planned", "normal", "routine", "anticipated"},
    "fraud": {"fraud", "fraudulent", "dispute", "disputed", "unauthorized", "suspicious"},
    "healthy": {"healthy", "strong", "good", "solid"},
    "low": {"low", "only", "below", "under", "limited", "short"},
    "margin": {"margin", "profit", "surplus"},
    "monitor": {"monitor", "monitoring", "watch", "track", "tracking"},
    "new": {"new", "first"},
    "pattern": {"pattern", "trend", "continued", "consistent", "repeated", "recurring"},
    "urgent": {"urgent", "urgency", "critical", "immediate", "emergency", "crisis", "danger"},
    "threshold": {"threshold", "minimum", "limit", "benchmark"},
    "variance": {"variance", "variation", "deviation", "fluctuation", "fluctuations"},
    "vendor": {"vendor", "vendors", "supplier", "suppliers"},
}


def _normalise(text: str) -> str:
    text = text.lower().replace("’", "'").replace("`", "'")
    return re.sub(r"\s+", " ", text).strip()


def _decimal(raw: str) -> Optional[Decimal]:
    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None


def _numbers(text: str) -> list[Decimal]:
    values: list[Decimal] = []
    for match in _NUMBER_RE.finditer(text):
        value = _decimal(match.group("number"))
        if value is None:
            continue
        unit = (match.group("unit") or "").lower()
        if unit == "k":
            value *= 1_000
        elif unit == "m":
            value *= 1_000_000
        values.append(value)
    return values


def _contains_number(values: list[Decimal], expected: Decimal) -> bool:
    return any(abs(value - expected) <= Decimal("0.01") for value in values)


def _has_ratio_pair(values: list[Decimal], ratio: Decimal) -> bool:
    for index, numerator in enumerate(values):
        for denominator in values[index + 1:]:
            if denominator == 0 or numerator == denominator:
                continue
            if abs((numerator / denominator) - ratio) < Decimal("0.06"):
                return True
    return False


def _numeric_matches(alternative: str, text: str) -> bool:
    """Match the numeric evidence in one criterion alternative."""
    text_values = _numbers(text)

    ratio_satisfied = False
    for ratio_match in re.finditer(r"(\d+(?:\.\d+)?)\s*x\b", alternative):
        ratio = _decimal(ratio_match.group(1))
        if ratio is not None and not _contains_number(text_values, ratio):
            if not _has_ratio_pair(text_values, ratio):
                return False
            ratio_satisfied = True

    if re.search(r"\b(double|twice)\b", alternative):
        if "double" not in text and "twice" not in text and not _contains_number(text_values, Decimal(2)):
            return False

    if "100%" in alternative and not any(value == 100 for value in text_values):
        return False

    threshold = re.search(
        r"(?:<|below|under|less than)\s*[$₹€£]?\s*(\d[\d,]*(?:\.\d+)?)",
        alternative,
    )
    if threshold:
        upper = _decimal(threshold.group(1))
        if upper is None or not any(value < upper for value in text_values):
            return False

    range_match = re.search(
        r"(\d[\d,]*(?:\.\d+)?)\s*(?:-|to)\s*(\d[\d,]*(?:\.\d+)?)",
        alternative,
    )
    if range_match:
        lower = _decimal(range_match.group(1))
        upper = _decimal(range_match.group(2))
        if lower is not None and upper is not None:
            if not any(lower <= value <= upper for value in text_values):
                return False

    at_least = re.search(r"\bat least\s+(\d+)", alternative)
    if at_least:
        minimum = _decimal(at_least.group(1))
        if minimum is not None and not any(value >= minimum for value in text_values):
            return False

    expected_values = _numbers(alternative)
    if expected_values and not threshold and not range_match and not ratio_satisfied:
        if not all(_contains_number(text_values, expected) for expected in expected_values):
            return False

    return True


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _word_present(word: str, text: str, text_words: set[str]) -> bool:
    if word in text_words or f"{word} " in f"{text} ":
        return True
    if word in _CONCEPTS:
        return any(candidate in text_words for candidate in _CONCEPTS[word])
    stem = _stem(word)
    if stem in _CONCEPTS:
        return any(candidate in text_words for candidate in _CONCEPTS[stem])
    if len(stem) >= 4:
        return any(candidate.startswith(stem) for candidate in text_words)
    return False


def _keywords(alternative: str, has_numbers: bool) -> list[str]:
    cleaned = re.sub(r"\([^)]*\)", " ", alternative)
    if "/" in cleaned:
        cleaned = cleaned.replace("/", " ")
    words = re.findall(r"[a-z0-9]+", cleaned)
    required = []
    for word in words:
        if word in _STOPWORDS or any(character.isdigit() for character in word):
            continue
        if has_numbers and word in _GENERIC_WITH_NUMBERS:
            continue
        required.append(word)
    return required


def _match_alternative(alternative: str, text: str, vendor: str) -> bool:
    text = _normalise(text)
    alternative = _normalise(alternative)

    if not _numeric_matches(alternative, text):
        return False

    required = _keywords(alternative, has_numbers=bool(_numbers(alternative)))
    text_words = set(re.findall(r"[a-z0-9]+", text))

    if "vendor" in required and vendor and _normalise(vendor) in text:
        return True

    for word in required:
        if not _word_present(word, text, text_words):
            return False
    return True


def _is_optional(criterion: str) -> bool:
    lowered = _normalise(criterion)
    return any(marker in lowered for marker in _OPTIONAL_MARKERS)


def _is_negative(criterion: str) -> bool:
    lowered = _normalise(criterion)
    if lowered.startswith("no "):
        return True
    return any(
        phrase in lowered
        for phrase in ("no alarm", "no urgency", "no error", "no urgent")
    )


def _negative_matches(criterion: str, text: str) -> bool:
    lowered = _normalise(criterion)
    text = _normalise(text)
    if "error" in lowered:
        forbidden = ("error", "failed", "failure", "exception", "invalid", "bug")
    elif "alarm" in lowered:
        forbidden = (
            "alarm", "alert", "critical", "danger", "emergency", "crisis", "panic",
        )
    else:
        forbidden = (
            "urgent", "critical", "danger", "emergency", "crisis", "immediate", "panic",
        )
    return not any(word in text for word in forbidden)


def criterion_matches(
    criterion: str,
    text: str,
    context: str = "",
    vendor: str = "",
) -> Optional[bool]:
    """Return whether ``criterion`` is evidenced by ``text``.

    ``None`` means the criterion is optional and must not affect scoring.
    """
    if _is_optional(criterion):
        return None
    if _is_negative(criterion):
        return _negative_matches(criterion, text)

    lowered = _normalise(criterion)

    action_aliases = {
        "check": {"check", "checks", "checking", "verify", "verifies", "verifying", "review", "reviews", "reviewing"},
        "verify": {"verify", "verifies", "verifying", "check", "checks", "checking"},
        "review": {"review", "reviews", "reviewing", "audit", "audits", "inspect", "inspects"},
        "investigate": {"investigate", "investigating", "investigation"},
        "contact": {"contact", "contacting", "reach", "call"},
        "monitor": {"monitor", "monitoring", "watch", "track", "tracking"},
    }
    if lowered.startswith(("suggests ", "recommends ")):
        text_words = set(re.findall(r"[a-z0-9]+", _normalise(text)))
        action_roots = {
            "check": ("check", "verif", "review", "audit", "inspect"),
            "verify": ("verif", "check"),
            "review": ("review", "audit", "inspect"),
            "investigate": ("investigat",),
            "contact": ("contact", "reach", "call"),
            "monitor": ("monitor", "watch", "track"),
        }
        for action, aliases in action_aliases.items():
            if any(root in lowered for root in action_roots[action]) and any(
                alias in text_words for alias in aliases
            ):
                return True

    if "identical" in lowered and "amount" in lowered:
        values = _numbers(text)
        if any(
            abs(first - second) <= Decimal("0.01")
            for index, first in enumerate(values)
            for second in values[index + 1:]
        ):
            return True

    for prefix in ("mentions that ", "mentions ", "suggests ", "recommends "):
        if lowered.startswith(prefix):
            lowered = lowered[len(prefix):]
            break

    alternatives = [part.strip() for part in re.split(r"\s+or\s+", lowered) if part.strip()]
    if not alternatives:
        return False
    return any(_match_alternative(alternative, text, vendor) for alternative in alternatives)
