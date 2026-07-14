"""
Base Agent for OntologyAI v1.0 - All 5 Python Agents.

Provides common functionality:
- AgentResult dataclass with validation
- Banned jargon list for plain English
- Qdrant memory writing
- Agent output persistence
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import uuid


# Banned jargon - plain English only
BANNED_JARGON = [
    "leverage",
    "synergy",
    "paradigm",
    "disrupt",
    "ecosystem",
    "holistic",
    "scalable",
    "robust",
    "seamless",
    "cutting-edge",
    "best-in-class",
    "game-changer",
    "mission-critical",
    "actionable",
    "granular",
    "proactive",
    "reactive",
    "incentivize",
    "optimize",
    "streamline",
    "empower",
    "facilitate",
    "utilize",
    "implement",
    "strategic",
    "tactical",
    "operational",
    "bandwidth",
    "capacity",
    "throughput",
    "latency",
    "overhead",
    "bottleneck",
    "pipeline",
    "funnel",
    "conversion",
    "engagement",
    "retention",
    "cohort",
    "segment",
    "journey",
    "touchpoint",
    "stakeholder",
    "deliverable",
    "milestone",
    "roadmap",
    "backlog",
    "sprint",
    "iteration",
    "agile",
    "scrumban",
    "kanban",
    "scrum",
    "devops",
    "cicd",
    "infrastructure",
    "architecture",
    "framework",
    "platform",
    "solution",
    "capability",
    "functionality",
    "feature-rich",
    "full-stack",
    "end-to-end",
    "cross-platform",
    "multi-tenant",
    "cloud-native",
    "serverless",
    "microservices",
    "monolithic",
    "modular",
    "extensible",
    "configurable",
    "customizable",
    "flexible",
    "adaptive",
    "intelligent",
    "smart",
    "automated",
    "ai-powered",
    "ml-driven",
    "data-driven",
    "insights",
    "analytics",
    "metrics",
    "kpis",
    "okrs",
    "kpi",
    "okr",
]


@dataclass
class AgentResult:
    """
    Standard result structure for all OntologyAI agents.

    Attributes:
        tenant_id: Tenant identifier
        agent_name: Name of the agent that produced this result
        fire_telegram: Whether to send a Telegram alert
        urgency: Alert urgency level (critical, high, warn, low)
        headline: One-line alert message in plain English
        do_this: Actionable next step for the founder
        is_good_news: Whether this is positive news (celebration)
        output_json: Additional structured data
        agent_output_id: Database ID of persisted output
        qdrant_point_id: Qdrant memory point ID
    """
    tenant_id: str
    agent_name: str = "unknown"
    fire_telegram: bool = False
    urgency: str = "low"
    headline: str = ""
    do_this: str = ""
    is_good_news: bool = False
    output_json: Dict[str, Any] = field(default_factory=dict)
    agent_output_id: Optional[str] = None
    qdrant_point_id: Optional[str] = None

    def validate_tone(self) -> List[str]:
        """
        Validate that output contains no banned jargon.

        Returns:
            List of violations (empty if valid)
        """
        violations = []
        text_to_check = f"{self.headline} {self.do_this}".lower()

        for term in BANNED_JARGON:
            if term.lower() in text_to_check:
                violations.append(f"Banned term: '{term}'")

        return violations

    def __post_init__(self) -> None:
        """Validate urgency level."""
        valid_urgency = {"critical", "high", "warn", "low"}
        if self.urgency not in valid_urgency:
            raise ValueError(
                f"Invalid urgency '{self.urgency}'. Must be one of: {valid_urgency}"
            )


class BaseAgent:
    """
    Base class for all OntologyAI v1.0 agents.

    Provides common methods for:
    - Qdrant memory writing
    - Agent output persistence
    - Tone validation
    """

    agent_name: str = "base_agent"

    def __init__(self) -> None:
        """Initialize base agent."""
        pass

    def run(self, state: dict, event: dict) -> dict:
        """
        Execute agent logic. Must be overridden by subclasses.

        Args:
            state: Current agent state
            event: Triggering event

        Returns:
            Agent result as dictionary

        Raises:
            NotImplementedError: If not overridden
        """
        raise NotImplementedError("Subclasses must implement run()")

    def _write_qdrant_memory(
        self,
        tenant_id: str,
        text: str,
        category: str = "general",
    ) -> str:
        """
        Write memory to Qdrant vector store.

        Args:
            tenant_id: Tenant identifier
            text: Memory text to store
            category: Memory category for filtering

        Returns:
            Qdrant point ID
        """
        from src.memory.qdrant_ops import upsert_memory

        # Map category to memory_type
        memory_type_map = {
            "anomaly": "anomaly",
            "briefing": "briefing",
            "revenue_event": "revenue_event",
            "general": "general",
        }
        memory_type = memory_type_map.get(category, category)

        point_id = upsert_memory(
            tenant_id=tenant_id,
            content=text,
            memory_type=memory_type,
            agent=self.agent_name,
        )
        return point_id

    def _write_agent_output(
        self,
        tenant_id: str,
        result: AgentResult,
    ) -> str:
        """
        Persist agent output to database.

        Args:
            tenant_id: Tenant identifier
            result: Agent result to persist

        Returns:
            Database record ID
        """
        from src.db.agent_outputs import insert_agent_output

        # Determine output_type from urgency
        output_type = result.urgency if result.urgency in ("critical", "high", "warn") else None

        record_id = insert_agent_output(
            tenant_id=tenant_id,
            agent_name=result.agent_name,
            headline=result.headline,
            urgency=result.urgency,
            hitl_sent=result.fire_telegram,
            output_json=result.output_json,
            output_type=output_type,
        )

        # Also write to hitl_actions if fire_telegram is True
        if result.fire_telegram and result.headline:
            from src.db.hitl_actions import insert_hitl_action

            # Determine buttons based on agent type and urgency
            buttons = self._get_default_buttons(result.urgency)

            insert_hitl_action(
                tenant_id=tenant_id,
                agent_name=result.agent_name,
                message_sent=result.headline,
                buttons=buttons,
            )

        return record_id

    def _get_default_buttons(self, urgency: str) -> list[str]:
        """
        Get default callback buttons based on urgency.

        Args:
            urgency: Urgency level

        Returns:
            List of button labels
        """
        if urgency == "critical":
            return ["Acknowledge", "Investigate", "Escalate"]
        elif urgency == "high":
            return ["Investigate", "Mark OK", "Send Reminder"]
        elif urgency == "warn":
            return ["Review", "Mark OK", "Snooze"]
        else:
            return ["Acknowledge", "Dismiss"]
