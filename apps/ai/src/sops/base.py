"""
Base classes for TrackGuard SOP Runtime.

All SOPs must inherit from BaseSOP and implement execute().
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import Any, Optional


# Banned jargon list — all SOP outputs must be jargon-free
BANNED_JARGON = [
    "leverage",
    "synergy",
    "synergies",
    "utilize",
    "streamline",
    "paradigm",
    "robust",
    "scalable",
    "proactive",
    "best-in-class",
    "cutting-edge",
    "world-class",
    "mission-critical",
    "actionable insights",
    "data-driven",
    "optimize",
    "holistic",
    "seamless",
]


class SOPResult(BaseModel):
    """
    Standard output format for all SOPs.

    Attributes:
        sop_name: Name of the SOP that produced this result
        founder_id: Founder who owns this SOP execution
        success: Whether the SOP completed successfully
        fire_alert: Whether this should trigger a founder alert
        hitl_risk: HITL risk level (low | medium | high)
        headline: One-line summary (jargon-free)
        do_this: Single action item (jargon-free)
        is_good_news: Whether this is positive news
        output: Raw structured output from SOP
        error: Error message if failed
        trace_id: Distributed tracing ID (for Langfuse)
    """
    sop_name:      str
    founder_id:    str
    success:       bool
    fire_alert:    bool = False
    hitl_risk:     str = "low"  # low | medium | high
    headline:      str = ""
    do_this:       str = ""
    is_good_news:  bool = False
    output:        dict = Field(default_factory=dict)
    error:         Optional[str] = None
    trace_id:      Optional[str] = None

    def validate_tone(self) -> list[str]:
        """
        Validate output is jargon-free.

        Returns:
            List of violation strings (empty if clean)
        """
        violations = []
        for term in BANNED_JARGON:
            for field in [self.headline, self.do_this]:
                if term.lower() in field.lower():
                    violations.append(f"Banned term '{term}' in output")
        return violations

    def is_valid(self) -> bool:
        """Check if result passes all validations."""
        return len(self.validate_tone()) == 0


class BaseSOP(ABC):
    """
    Abstract base class for all TrackGuard SOPs.

    All SOPs must:
    1. Define sop_name class attribute
    2. Implement execute() method

    Usage:
        class MySOP(BaseSOP):
            sop_name = "SOP_MY_SOP"

            async def execute(self, payload_ref: str, founder_id: str) -> SOPResult:
                # Fetch payload from PostgreSQL
                raw = self.fetch_payload(payload_ref)
                # ... SOP logic ...
                return SOPResult(...)
    """
    sop_name: str

    @abstractmethod
    async def execute(self, payload_ref: str, founder_id: str) -> SOPResult:
        """
        Execute the SOP.

        Args:
            payload_ref: Reference to payload storage ("raw_events:<uuid>")
            founder_id: Founder who owns this SOP execution

        Returns:
            SOPResult with execution outcome
        """
        pass

    def fetch_payload(self, payload_ref: str) -> dict:
        """
        Resolve payload_ref → PostgreSQL row → return parsed dict.

        Args:
            payload_ref: Storage reference (e.g., "raw_events:uuid-123")

        Returns:
            Parsed payload dict

        Raises:
            ValueError: If payload_ref format is invalid
        """
        from src.db.raw_events import fetch_raw_event_by_id

        if ":" not in payload_ref:
            raise ValueError(f"Invalid payload_ref format: {payload_ref!r}")

        prefix, ref_id = payload_ref.split(":", 1)

        if prefix == "raw_events":
            return fetch_raw_event_by_id(ref_id)
        elif prefix == "files":
            # Read file from disk/S3
            raise NotImplementedError("File payload fetch not yet implemented")
        else:
            raise ValueError(f"Unknown payload_ref prefix: {prefix!r}")

    class Config:
        """Pydantic config for BaseSOP."""
        arbitrary_types_allowed = True
