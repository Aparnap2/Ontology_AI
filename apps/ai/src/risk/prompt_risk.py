"""Prompt Risk Scanner — deterministic pre-generation scan.

Scans assembled prompts for restricted content, customer PII,
investor-sensitive phrasing, and disallowed external-send actions
before any LLM invocation.
"""
from __future__ import annotations

import logging
import re

from src.schemas.control_plane import RiskFlag, RiskScanResult, RiskSeverity

log = logging.getLogger(__name__)

# Restricted tokens that should never appear in prompts sent to LLMs
_RESTRICTED_PATTERNS: list[tuple[str, str, RiskSeverity]] = [
    ("R001", r"(?i)(api[_-]?key|secret[_-]?key|password|auth[_-]?token)\s*[:=]\s*['\"]?\w{16,}", RiskSeverity.HIGH),
    ("R002", r"(?i)(sk-[a-zA-Z0-9]{20,}|pk-[a-zA-Z0-9]{20,})", RiskSeverity.HIGH),
]

# Customer-identifying patterns
_CUSTOMER_PII_PATTERNS: list[tuple[str, str, RiskSeverity]] = [
    ("P001", r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", RiskSeverity.MEDIUM),
    ("P002", r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", RiskSeverity.HIGH),
]

# Investor-sensitive phrasing — claims that need disclaimers
_INVESTOR_SENSITIVE_KEYWORDS: list[tuple[str, str, RiskSeverity]] = [
    ("I001", r"(?i)(projected|forecast|guidance|will\s+(grow|hit|reach|achieve|deliver))", RiskSeverity.MEDIUM),
    ("I002", r"(?i)(revenue\s+(run[-\s]?rate|projection|target)|mrr\s+projection)", RiskSeverity.MEDIUM),
    ("I003", r"(?i)(ipo|acquisition\s+offer|exit\s+strategy|series\s+[abcde])", RiskSeverity.MEDIUM),
]

# Disallowed external-send action patterns
_EXTERNAL_SEND_PATTERNS: list[tuple[str, str, RiskSeverity]] = [
    ("E001", r"(?i)(send\s+(this|the|an?\s+(email|update|draft))|email\s+(to|the|this))", RiskSeverity.HIGH),
    ("E002", r"(?i)(post\s+(to|on|this)|publish\s+(this|the)|share\s+(with|externally))", RiskSeverity.HIGH),
]

_ALL_PATTERNS = _RESTRICTED_PATTERNS + _CUSTOMER_PII_PATTERNS + _INVESTOR_SENSITIVE_KEYWORDS + _EXTERNAL_SEND_PATTERNS


def scan_prompt(text: str, context: str | None = None) -> RiskScanResult:
    """Scan prompt text for risk flags before LLM invocation.

    Args:
        text: The prompt or assembled input text to scan.
        context: Optional context hint (e.g. "investor_update", "customer_email").

    Returns:
        RiskScanResult with any flags detected.
    """
    flags: list[RiskFlag] = []
    highest_severity: RiskSeverity = RiskSeverity.LOW

    for rule_id, pattern, severity in _ALL_PATTERNS:
        matches = re.findall(pattern, text)
        if matches:
            matched_text = str(matches[0]) if matches else ""
            # Truncate matched text for display
            if len(matched_text) > 80:
                matched_text = matched_text[:77] + "..."
            flags.append(RiskFlag(
                rule_id=rule_id,
                description=_get_rule_description(rule_id),
                severity=severity,
                matched_text=matched_text,
            ))

    if flags:
        status = "flag"
        highest_severity = max((f.severity for f in flags), key=_severity_rank)
        if highest_severity == RiskSeverity.HIGH or context in ("investor_update", "customer_email"):
            recommended_action = "block"
        elif highest_severity == RiskSeverity.MEDIUM:
            recommended_action = "review"
        else:
            recommended_action = "proceed"
    else:
        status = "pass"
        recommended_action = "proceed"

    return RiskScanResult(
        status=status,
        flags=flags,
        severity=highest_severity,
        recommended_action=recommended_action,
    )


def _severity_rank(s: RiskSeverity) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get(s.value, 0)


def _get_rule_description(rule_id: str) -> str:
    descriptions = {
        "R001": "Prompt contains credentials or secrets",
        "R002": "Prompt contains API key pattern",
        "P001": "Prompt contains email address",
        "P002": "Prompt contains phone number pattern",
        "I001": "Prompt contains forward-looking statement",
        "I002": "Prompt contains revenue projection",
        "I003": "Prompt contains exit/valuation language",
        "E001": "Prompt contains send action instruction",
        "E002": "Prompt contains publish/share action instruction",
    }
    return descriptions.get(rule_id, f"Unknown rule: {rule_id}")
