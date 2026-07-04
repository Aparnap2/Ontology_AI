"""Output Risk Scanner — deterministic post-generation scan.

Scans generated drafts for unsupported claims, promises,
pricing commitments, investor misstatements, or missing
approval state before any send action is permitted.
"""
from __future__ import annotations

import logging
import re

from src.schemas.control_plane import RiskFlag, RiskScanResult, RiskSeverity

log = logging.getLogger(__name__)

# Unsupported claim patterns — specific numbers presented as projections
_UNSUPPORTED_CLAIMS: list[tuple[str, str, RiskSeverity]] = [
    ("OC001", r"(?i)(growing\s+\d+%\s+(MoM|YoY|month|year)|(\d+[-×x])\d+%\s+growth)", RiskSeverity.HIGH),
    ("OC002", r"(?i)(on\s+track\s+to\s+(hit|reach|achieve)\s+\$?[\d,.]+[kKmMbB]?)", RiskSeverity.HIGH),
]

# Promise/commitment patterns
_PROMISE_PATTERNS: list[tuple[str, str, RiskSeverity]] = [
    ("OC003", r"(?i)(guarantee|guaranteed|promise|promised|ensure|assure|will\s+definitely|certainly)", RiskSeverity.HIGH),
    ("OC004", r"(?i)(we\s+(will|shall)\s+(always|never|absolutely|unconditionally))", RiskSeverity.MEDIUM),
]

# Pricing commitment patterns
_PRICING_PATTERNS: list[tuple[str, str, RiskSeverity]] = [
    ("OC005", r"(?i)(price\s+(freeze|lock|guarantee)|no\s+price\s+increase|flat\s+pricing)", RiskSeverity.HIGH),
    ("OC006", r"(?i)(discount\s+(of\s+)?\d+%|reduced\s+(to|by)\s+\$?[\d,.]+)", RiskSeverity.MEDIUM),
]

# Investor misstatement patterns
_INVESTOR_MISSTATEMENTS: list[tuple[str, str, RiskSeverity]] = [
    ("OC007", r"(?i)(outpacing\s+(competitors|market|industry)|disrupting\s+the\s+\w+\s+industry)", RiskSeverity.MEDIUM),
    ("OC008", r"(?i)(comparable\s+to\s+[A-Z][a-z]+(\s+[A-Z][a-z]+)?\s+(at\s+)?(our|similar)\s+stage)", RiskSeverity.MEDIUM),
]

# Missing approval state — output should indicate it's a draft
_MISSING_APPROVAL = [
    ("OC009", r"(?i)(draft|for\s+review|pending\s+approval|needs\s+review|not\s+final)", RiskSeverity.LOW),
]

_ALL_OUTPUT_PATTERNS = _UNSUPPORTED_CLAIMS + _PROMISE_PATTERNS + _PRICING_PATTERNS + _INVESTOR_MISSTATEMENTS + _MISSING_APPROVAL


def scan_output(text: str, context: str | None = None) -> RiskScanResult:
    """Scan generated output text for risk flags before release.

    Args:
        text: The generated draft or output text to scan.
        context: Optional context hint (e.g. "investor_update", "customer_email").

    Returns:
        RiskScanResult with any flags detected.
    """
    flags: list[RiskFlag] = []
    highest_severity: RiskSeverity = RiskSeverity.LOW
    has_draft_disclaimer = False

    for rule_id, pattern, severity in _MISSING_APPROVAL:
        if re.search(pattern, text):
            has_draft_disclaimer = True
            break

    for rule_id, pattern, severity in _ALL_OUTPUT_PATTERNS:
        matches = re.findall(pattern, text)
        if matches:
            matched_text = str(matches[0]) if matches else ""
            if len(matched_text) > 80:
                matched_text = matched_text[:77] + "..."
            flags.append(RiskFlag(
                rule_id=rule_id,
                description=_get_output_rule_description(rule_id),
                severity=severity,
                matched_text=matched_text,
            ))

    # If context is investor-facing and no draft disclaimer found, add a warning
    if context in ("investor_update", "customer_email") and not has_draft_disclaimer:
        flags.append(RiskFlag(
            rule_id="OC009",
            description="Output is missing draft/pending-review disclaimer",
            severity=RiskSeverity.LOW,
            matched_text="(no draft disclaimer found)",
        ))

    if flags:
        status = "flag"
        highest_severity = max((f.severity for f in flags), key=_severity_rank)
        if highest_severity == RiskSeverity.HIGH:
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


def _get_output_rule_description(rule_id: str) -> str:
    descriptions = {
        "OC001": "Output contains unsupported growth claim",
        "OC002": "Output contains unsupported revenue projection",
        "OC003": "Output contains guarantee or promise",
        "OC004": "Output contains absolute commitment language",
        "OC005": "Output contains pricing commitment",
        "OC006": "Output contains discount promise",
        "OC007": "Output contains misleading competitive claim",
        "OC008": "Output contains false comparable claim",
        "OC009": "Output is missing draft/pending-review disclaimer",
    }
    return descriptions.get(rule_id, f"Unknown rule: {rule_id}")
