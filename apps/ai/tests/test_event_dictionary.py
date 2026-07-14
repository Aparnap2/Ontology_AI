"""Test suite for Event Dictionary (v1.0 — 4 agents)."""
import pytest
from src.config.event_dictionary import EventDictionary, UnknownEventError


class TestEventDictionary:
    """Test EventDictionary for OntologyAI v1.0."""

    def setup_method(self):
        """Set up test fixtures."""
        self.d = EventDictionary()

    def test_telegram_query_inbound_maps_to_chief_of_staff(self):
        """Telegram QUERY_INBOUND should route to ChiefOfStaffAgent."""
        entry = self.d.resolve(source="telegram", event_type="QUERY_INBOUND")
        assert entry.agent_name == "ChiefOfStaffAgent"
        assert "Chief of Staff" in entry.employees

    def test_cron_daily_tick_maps_to_pulse(self):
        """Cron DAILY_TICK should route to PulseAgent."""
        entry = self.d.resolve(source="cron", event_type="DAILY_TICK")
        assert entry.agent_name == "PulseAgent"
        assert "Pulse Monitor" in entry.employees

    def test_cron_weekly_briefing_maps_to_chief_of_staff(self):
        """Cron WEEKLY_BRIEFING should route to ChiefOfStaffAgent."""
        entry = self.d.resolve(source="cron", event_type="WEEKLY_BRIEFING")
        assert entry.agent_name == "ChiefOfStaffAgent"
        assert "Chief of Staff" in entry.employees

    def test_unknown_event_raises(self):
        """Unknown events should raise UnknownEventError."""
        with pytest.raises(UnknownEventError):
            self.d.resolve(source="stripe", event_type="payment.captured")

    def test_unknown_source_raises(self):
        """Unknown sources should raise UnknownEventError."""
        with pytest.raises(UnknownEventError):
            self.d.resolve(source="unknown_source", event_type="UNKNOWN_EVENT")

    def test_no_duplicate_source_event_pairs(self):
        """No duplicate (source, event_type) pairs should exist."""
        entries = self.d.all_entries()
        keys = [(e.source, e.event_type) for e in entries]
        assert len(keys) == len(set(keys)), "Duplicate (source, event_type) pairs found"

    def test_all_razorpay_events(self):
        """All Razorpay events should be registered (5 events)."""
        razorpay_events = self.d.by_source("razorpay")
        assert len(razorpay_events) == 0, f"Expected 0 Razorpay events, got {len(razorpay_events)}"

    def test_all_telegram_events(self):
        """All Telegram events should be registered (1 event)."""
        telegram_events = self.d.by_source("telegram")
        assert len(telegram_events) == 1, f"Expected 1 Telegram event, got {len(telegram_events)}"

    def test_all_cron_events(self):
        """All Cron events should be registered (2 events)."""
        cron_events = self.d.by_source("cron")
        assert len(cron_events) == 2, f"Expected 2 Cron events, got {len(cron_events)}"

    def test_pulse_agent_events(self):
        """PulseAgent should handle 1 event."""
        pulse_events = self.d.by_agent("PulseAgent")
        assert len(pulse_events) == 1, f"Expected 1 PulseAgent event, got {len(pulse_events)}"

    def test_chief_of_staff_events(self):
        """ChiefOfStaffAgent should handle 2 events."""
        cos_events = self.d.by_agent("ChiefOfStaffAgent")
        assert len(cos_events) == 2, f"Expected 2 ChiefOfStaffAgent events, got {len(cos_events)}"

    def test_total_event_count(self):
        """Total events should be 3 for v1.0."""
        total = self.d.count()
        assert total == 3, f"Expected 3 events for v1.0, got {total}"
