"""Pratihara — Alert Quality Gate.

Per Kautilyan architecture: the Gatekeeper controls access to the Swami.
Nothing reaches the founder without passing through the Pratihara.

Gate stages (in order):
1. Schema validation — alert matches AlertDecision schema
2. Trust check — agent not degraded
3. Dedup check — same alert not already sent in time window
4. Tone filter — output passes tone/quality check
5. Authority check — critical alerts need trust_score >= 0.8
6. Risk check — flag high financial-risk alerts
7. Privacy check — block alerts containing PII
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from src.services.state_store import StateStore

_DEDUP_WINDOW_MINUTES = 60

_REQUIRED_FIELDS = {"should_alert", "severity", "primary_signal"}
_OPTIONAL_FIELDS = {"headline", "explanation", "recommended_action"}

# PII patterns for privacy stage
_PII_PATTERN = re.compile(
    r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b"         # email
    r"|\b\d{3}[-.]\d{3}[-.]\d{4}\b"                # phone (US format)
    r"|\b\d{3}-\d{2}-\d{4}\b"                       # SSN
)


@dataclass
class GateResult:
    """Result of running the alert gate."""
    passed: bool
    stage: str  # Which stage blocked it: "schema" | "trust" | "dedup" | "tone" | "authority" | "risk" | "privacy" | "passed"
    reason: str
    alert: dict | None = None


class AlertGate:
    """Alert quality gate — Pratihara.

    Stages applied in order:
    1. Schema validation — required fields and types
    2. Trust check — agent's trust score not degraded
    3. Dedup check — same alert not sent in last 60 minutes
    4. Tone filter — basic text quality check (permissive fallback)
    5. Authority check — critical alerts need trust_score >= 0.8
    6. Risk check — flag high financial-risk alerts
    7. Privacy check — block alerts containing PII
    """

    def __init__(self, tenant_id: str) -> None:
        self.tenant_id: str = tenant_id
        self._dedup_store = StateStore(prefix=f"dedup:{tenant_id}")
        self._recent_alerts: dict[str, datetime] = {}  # L1 in-memory cache

    def check(
        self,
        alert: dict,
        agent_name: str,
        skip_tone: bool = False,
    ) -> GateResult:
        """Run alert through all gate stages.

        Stages execute in order. If any stage fails, processing stops
        and a failure GateResult is returned immediately.

        Args:
            alert: Alert dict with keys: should_alert, severity,
                   primary_signal, headline, explanation, etc.
            agent_name: Name of the agent that produced this alert
            skip_tone: Skip tone filter (for tests / emergencies)

        Returns:
            GateResult with pass/fail and which stage blocked it
        """
        # Stage 1: Schema validation
        valid, reason = self._validate_schema(alert)
        if not valid:
            return GateResult(passed=False, stage="schema", reason=reason, alert=alert)

        # Stage 2: Trust check
        valid, reason = self._check_trust(agent_name)
        if not valid:
            return GateResult(passed=False, stage="trust", reason=reason, alert=alert)

        # Stage 3: Dedup check
        valid, reason = self._check_dedup(alert, agent_name)
        if not valid:
            return GateResult(passed=False, stage="dedup", reason=reason, alert=alert)

        # Stage 4: Tone check
        if not skip_tone:
            valid, reason = self._check_tone(alert)
            if not valid:
                return GateResult(passed=False, stage="tone", reason=reason, alert=alert)

        # Stage 5: Authority check
        valid, reason = self._check_authority(agent_name, alert)
        if not valid:
            return GateResult(passed=False, stage="authority", reason=reason, alert=alert)

        # Stage 6: Risk check
        valid, reason = self._check_risk(alert)
        if not valid:
            return GateResult(passed=False, stage="risk", reason=reason, alert=alert)

        # Stage 7: Privacy check
        valid, reason = self._check_privacy(alert)
        if not valid:
            return GateResult(passed=False, stage="privacy", reason=reason, alert=alert)

        # All stages passed — register the dedup key
        dedup_key = self._make_dedup_key(agent_name, alert)
        now_str = datetime.now().isoformat()
        self._recent_alerts[dedup_key] = datetime.now()
        self._dedup_store.set(dedup_key, now_str, ttl=_DEDUP_WINDOW_MINUTES * 60)

        return GateResult(
            passed=True,
            stage="passed",
            reason="All gate stages passed",
            alert=alert,
        )

    # ── Stage 1: Schema validation ───────────────────────────────────────

    def _validate_schema(self, alert: dict) -> tuple[bool, str]:
        """Stage 1: Validate alert has required fields.

        Required: should_alert (bool), severity (str), primary_signal (str)
        Optional but noted: headline, explanation, recommended_action
        """
        if not isinstance(alert, dict):
            return False, "Alert must be a dict"

        for field in _REQUIRED_FIELDS:
            if field not in alert:
                return False, f"Missing required field: {field}"

        if not isinstance(alert.get("should_alert"), bool):
            return False, "should_alert must be a bool"

        valid_severities = {"critical", "warning", "info"}
        severity = alert.get("severity")
        if severity not in valid_severities:
            return False, f"severity must be one of {valid_severities}, got '{severity}'"

        if not isinstance(alert.get("primary_signal"), str) or not alert["primary_signal"].strip():
            return False, "primary_signal must be a non-empty string"

        # Warn about missing optional fields but don't block
        missing_optional = [f for f in _OPTIONAL_FIELDS if f not in alert]
        if missing_optional:
            return True, f"Missing optional fields: {', '.join(missing_optional)}"

        return True, "Schema valid"

    # ── Stage 2: Trust check ─────────────────────────────────────────────

    def _check_trust(self, agent_name: str) -> tuple[bool, str]:
        """Stage 2: Check agent trust score.

        If trust_score < 0.4 → BLOCK
        If trust_score < 0.6 → PASS but note caution
        """
        try:
            from src.services.trust_battery import get_profile, is_agent_degraded

            degraded = is_agent_degraded(self.tenant_id, agent_name)
            profile = get_profile(self.tenant_id, agent_name)

            if degraded:
                return (
                    False,
                    f"Agent '{agent_name}' is degraded "
                    f"(trust_score={profile.trust_score:.2f} < 0.4)",
                )

            if profile.trust_score < 0.6:
                return (
                    True,
                    f"Agent '{agent_name}' has low trust "
                    f"(trust_score={profile.trust_score:.2f}) — proceeding with caution",
                )

            return True, "Trust check passed"

        except ImportError:
            # If trust_battery is not available, pass permissively
            return True, "trust_battery not available (permissive)"

    # ── Stage 3: Dedup check ─────────────────────────────────────────────

    def _make_dedup_key(self, agent_name: str, alert: dict) -> str:
        """Generate dedup key from agent + severity + primary_signal."""
        severity = alert.get("severity", "unknown")
        signal = alert.get("primary_signal", "").strip().lower()
        return f"{agent_name}:{severity}:{signal}"

    def _check_dedup(self, alert: dict, agent_name: str) -> tuple[bool, str]:
        """Stage 3: Check for duplicate alerts in the dedup window.

        Generate dedup key from agent + severity + primary_signal.
        If same key sent within the dedup window → BLOCK.

        Checks L1 (in-memory cache) first, then L2 (StateStore).
        """
        dedup_key = self._make_dedup_key(agent_name, alert)

        now = datetime.now()
        last_sent = self._recent_alerts.get(dedup_key)

        # L1 miss — try L2 (StateStore)
        if last_sent is None:
            stored = self._dedup_store.get(dedup_key)
            if stored:
                try:
                    last_sent = datetime.fromisoformat(stored)
                    self._recent_alerts[dedup_key] = last_sent
                except (ValueError, TypeError):
                    pass

        if last_sent is not None:
            elapsed = now - last_sent
            if elapsed < timedelta(minutes=_DEDUP_WINDOW_MINUTES):
                remaining = _DEDUP_WINDOW_MINUTES - int(elapsed.total_seconds() / 60)
                return (
                    False,
                    f"Duplicate alert (key='{dedup_key}') "
                    f"sent {int(elapsed.total_seconds() / 60)}m ago — "
                    f"retry in ~{remaining}m",
                )

        return True, "No duplicate found"

    # ── Stage 4: Tone filter ─────────────────────────────────────────────

    def _check_tone(self, alert: dict) -> tuple[bool, str]:
        """Stage 4: Basic text quality check.

        Checks if the tone_filter module is importable, then performs
        a deterministic quality check on alert text (no LLM calls).
        If tone_filter is not available, passes permissively.
        """
        try:
            # Verify the tone_filter module is importable
            import importlib  # noqa: PLC0415

            importlib.import_module("src.services.tone_filter")
        except ImportError:
            return True, "tone_filter not available (permissive)"

        # Basic text quality check (deterministic, no LLM)
        text = (
            alert.get("headline")
            or alert.get("explanation")
            or alert.get("primary_signal")
            or alert.get("context_note")
            or ""
        )

        if not text or not text.strip():
            return False, "Alert text is empty"

        if len(text.strip()) < 10:
            return False, "Alert text is too short for meaningful delivery"

        return True, "Tone check passed"

    # ── Stage 5: Authority check ──────────────────────────────────────────

    def _check_authority(self, agent_name: str, alert: dict) -> tuple[bool, str]:
        """Stage 5: Authority check for critical alerts.

        If severity is "critical", the agent's trust score must be >= 0.8.
        Low-trust agents cannot issue critical alerts without review.

        Args:
            agent_name: Name of the agent that produced this alert.
            alert: The alert dict being evaluated.

        Returns:
            (True, reason) if check passes, (False, reason) if blocked.
        """
        severity = alert.get("severity", "info")
        if severity != "critical":
            return True, "Authority check passed (non-critical)"

        try:
            from src.services.trust_battery import get_profile

            profile = get_profile(self.tenant_id, agent_name)
            if profile.trust_score < 0.8:
                return (
                    False,
                    f"Authority check failed: critical alert requires trust_score >= 0.8 "
                    f"(got {profile.trust_score:.2f})",
                )
            return True, "Authority check passed (high-trust critical)"
        except ImportError:
            return True, "Authority check passed (trust_battery unavailable)"

    # ── Stage 6: Risk check ──────────────────────────────────────────────

    def _check_risk(self, alert: dict) -> tuple[bool, str]:
        """Stage 6: Financial risk assessment.

        If severity is "critical" AND the primary_signal contains
        financial risk indicators ("burn", "runway"), passes with
        a caveat. Never blocks — always permissive.

        Args:
            alert: The alert dict being evaluated.

        Returns:
            Always (True, reason) — this stage is informational.
        """
        severity = alert.get("severity", "info")
        primary_signal = alert.get("primary_signal", "").lower()
        if severity == "critical" and any(kw in primary_signal for kw in ["burn", "runway"]):
            return True, "Risk check passed: high financial risk noted"
        return True, "Risk check passed"

    # ── Stage 7: Privacy check ───────────────────────────────────────────

    def _check_privacy(self, alert: dict) -> tuple[bool, str]:
        """Stage 7: PII detection in alert content.

        Scans all alert text values for PII patterns (email, phone, SSN).
        If PII is detected, blocks the alert.

        Args:
            alert: The alert dict being evaluated.

        Returns:
            (True, reason) if no PII found, (False, reason) if PII detected.
        """
        text = " ".join(str(v) for v in alert.values())
        if _PII_PATTERN.search(text):
            return False, "Privacy check failed: alert contains PII"
        return True, "Privacy check passed"

    # ── Test helpers ─────────────────────────────────────────────────────

    def reset_dedup(self) -> None:
        """Clear dedup cache (for testing)."""
        self._recent_alerts.clear()
        self._dedup_store.clear_prefix()
