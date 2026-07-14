"""
Event Dictionary for OntologyAI v1.0.

Maps every (source, event_type) pair to exactly one agent.
Enforced in code — unknown events raise UnknownEventError.

Note: In v1.0, routing is handled by agents, not static topics/SOPs.
This dictionary is kept for backward compatibility and migration.
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class DictionaryEntry:
    """Single event mapping entry (v1.0 schema)."""
    source:     str
    event_type: str  # Normalized event type (e.g., "PAYMENT_SUCCESS")
    agent_name: str  # Agent that handles this event
    employees:  List[str] = field(default_factory=list)


class UnknownEventError(KeyError):
    """Raised when event is not in dictionary."""
    pass


# Registry of events for OntologyAI v1.0 (4 agents: Pulse, Anomaly, Investor, QA)
_REGISTRY: List[DictionaryEntry] = [
    # ── TELEGRAM ──────────────────────────────────────────────
    DictionaryEntry("telegram", "QUERY_INBOUND", "ChiefOfStaffAgent", ["Chief of Staff"]),

    # ── CRON ──────────────────────────────────────────────────
    DictionaryEntry("cron", "DAILY_TICK", "PulseAgent", ["Pulse Monitor"]),
    DictionaryEntry("cron", "WEEKLY_BRIEFING", "ChiefOfStaffAgent", ["Chief of Staff"]),
]


class EventDictionary:
    """
    Event dictionary for OntologyAI v1.0.

    Resolves (source, event_type) pairs to their corresponding
    agent and responsible employees.

    Usage:
        d = EventDictionary()
        entry = d.resolve(source="cron", event_type="DAILY_TICK")
        print(entry.agent_name)  # "PulseAgent"
        print(entry.employees)   # ["Pulse Monitor"]
    """

    def __init__(self):
        self._index = {(e.source, e.event_type): e for e in _REGISTRY}

    def resolve(self, source: str, event_type: str) -> DictionaryEntry:
        """
        Resolve (source, event_type) to DictionaryEntry.

        Args:
            source: Event source (razorpay, bank, telegram, cron, internal)
            event_type: Normalized event type (PAYMENT_SUCCESS, etc.)

        Returns:
            DictionaryEntry with agent_name and employees

        Raises:
            UnknownEventError: If (source, event_type) not in dictionary
        """
        key = (source, event_type)
        if key not in self._index:
            raise UnknownEventError(
                f"No mapping for source='{source}' event_type='{event_type}'. "
                f"Add it to event_dictionary.py before handling."
            )
        return self._index[key]

    def all_entries(self) -> List[DictionaryEntry]:
        """Return all dictionary entries."""
        return list(self._index.values())

    def count(self) -> int:
        """Return total number of registered events."""
        return len(self._index)

    def by_agent(self, agent_name: str) -> List[DictionaryEntry]:
        """Return all events handled by a specific agent."""
        return [e for e in self._index.values() if e.agent_name == agent_name]

    def by_source(self, source: str) -> List[DictionaryEntry]:
        """Return all events from a specific source."""
        return [e for e in self._index.values() if e.source == source]
