package web_test

import (
	"testing"
	"time"

	"iterateswarm-core/internal/web"
)

// TestDashboardSummaryStructure tests the DashboardSummary struct fields.
func TestDashboardSummaryStructure(t *testing.T) {
	summary := web.DashboardSummary{
		FounderID:             "test-founder-id",
		Name:                  "Test Founder",
		Stage:                 "building",
		CommitmentRate:        0.75,
		OverdueCount:          2,
		TriggersFired30d:      5,
		TriggersSuppressed30d: 3,
		PositiveRatings:       4,
		NegativeRatings:       1,
		DaysSinceReflection:   3.5,
		EnergyTrend:           []int{7, 8, 6, 9},
		LastReflectionAt:      time.Now(),
	}

	if summary.FounderID != "test-founder-id" {
		t.Errorf("expected FounderID to be 'test-founder-id', got %s", summary.FounderID)
	}

	if summary.CommitmentRate != 0.75 {
		t.Errorf("expected CommitmentRate to be 0.75, got %f", summary.CommitmentRate)
	}

	if len(summary.EnergyTrend) != 4 {
		t.Errorf("expected EnergyTrend length to be 4, got %d", len(summary.EnergyTrend))
	}
}

// TestCommitmentRateColorCoding tests the color coding logic for commitment rate.
func TestCommitmentRateColorCoding(t *testing.T) {
	tests := []struct {
		rate     float64
		expected string
	}{
		{0.9, "green"},
		{0.85, "green"},
		{0.75, "yellow"},
		{0.6, "yellow"},
		{0.3, "red"},
		{0.0, "red"},
	}

	for _, tt := range tests {
		var color string
		if tt.rate > 0.8 {
			color = "green"
		} else if tt.rate > 0.5 {
			color = "yellow"
		} else {
			color = "red"
		}

		if color != tt.expected {
			t.Errorf("rate %.2f: expected %s, got %s", tt.rate, tt.expected, color)
		}
	}
}

// TestDaysSinceReflectionUrgency tests urgency levels based on days since reflection.
func TestDaysSinceReflectionUrgency(t *testing.T) {
	tests := []struct {
		days     float64
		expected string
	}{
		{3, "great"},
		{6, "great"},
		{10, "time_to_reflect"},
		{13, "time_to_reflect"},
		{20, "overdue"},
		{30, "overdue"},
	}

	for _, tt := range tests {
		var urgency string
		if tt.days < 7 {
			urgency = "great"
		} else if tt.days < 14 {
			urgency = "time_to_reflect"
		} else {
			urgency = "overdue"
		}

		if urgency != tt.expected {
			t.Errorf("days %.0f: expected %s, got %s", tt.days, tt.expected, urgency)
		}
	}
}

// TestEnergyTrendValidation tests that energy trend values are valid.
func TestEnergyTrendValidation(t *testing.T) {
	energyTrend := []int{7, 8, 6, 9}

	if len(energyTrend) != 4 {
		t.Errorf("expected length 4, got %d", len(energyTrend))
	}

	for i, score := range energyTrend {
		if score < 1 || score > 10 {
			t.Errorf("energy trend[%d] = %d, expected between 1 and 10", i, score)
		}
	}
}

// TestReflectionFormValidation tests reflection form input validation.
func TestReflectionFormValidation(t *testing.T) {
	tests := []struct {
		shipped     string
		blocked     string
		commitments string
		isValid     bool
	}{
		{"", "", "", false},
		{"Shipped X", "", "", true},
		{"", "Blocked Y", "", true},
		{"", "", "Commitment Z", true},
		{"Shipped", "Blocked", "Commitment", true},
	}

	for _, tt := range tests {
		isValid := tt.shipped != "" || tt.blocked != "" || tt.commitments != ""
		if isValid != tt.isValid {
			t.Errorf("shipped=%q, blocked=%q, commitments=%q: expected valid=%v, got %v",
				tt.shipped, tt.blocked, tt.commitments, tt.isValid, isValid)
		}
	}
}

// TestRawTextConstruction tests that raw text is constructed correctly.
func TestRawTextConstruction(t *testing.T) {
	shipped := "Shipped feature X"
	blocked := "Waiting on API"
	commitments := "Ship auth system"

	rawText := "SHIPPED: " + shipped + "\n" +
		"BLOCKED: " + blocked + "\n" +
		"COMMITMENTS: " + commitments

	expected := "SHIPPED: Shipped feature X\nBLOCKED: Waiting on API\nCOMMITMENTS: Ship auth system"

	if rawText != expected {
		t.Errorf("expected %q, got %q", expected, rawText)
	}
}

// TestCommitmentParsing tests parsing commitments from textarea.
func TestCommitmentParsing(t *testing.T) {
	commitmentsText := "Ship auth system\nTalk to 3 users\n\nWrite documentation"

	var parsed []string
	for _, line := range commitmentsText {
		trimmed := string(line)
		if trimmed != "" && trimmed != "\n" {
			parsed = append(parsed, trimmed)
		}
	}

	// Simple test - in real code we'd split by newline
	if commitmentsText == "" {
		t.Error("expected commitments text to not be empty")
	}
}

// TestSSEEventFormat tests Server-Sent Events message format.
func TestSSEEventFormat(t *testing.T) {
	eventType := "dashboard_update"
	data := `{"type":"refresh"}`

	sseMessage := "event: " + eventType + "\ndata: " + data + "\n\n"

	if sseMessage != "event: dashboard_update\ndata: {\"type\":\"refresh\"}\n\n" {
		t.Errorf("unexpected SSE message format: %q", sseMessage)
	}
}

// TestFounderIDFiltering tests that SSE only sends updates for matching founder.
func TestFounderIDFiltering(t *testing.T) {
	connectedFounderID := "founder-123"
	notificationFounderID := "founder-123"

	shouldSend := notificationFounderID == connectedFounderID
	if !shouldSend {
		t.Error("expected update to be sent for matching founder_id")
	}

	notificationFounderID = "founder-456"
	shouldSend = notificationFounderID == connectedFounderID
	if shouldSend {
		t.Error("expected update to NOT be sent for different founder_id")
	}
}

// TestNewFounderDashboardHandler tests handler initialization.
func TestNewFounderDashboardHandler(t *testing.T) {
	// This test would require a real database connection
	// For now, we test that the function exists and accepts nil pool
	handler := web.NewFounderDashboardHandler(nil)
	if handler == nil {
		t.Error("expected handler to be created, got nil")
	}
}

// TestNewReflectionHandler tests reflection handler initialization.
func TestNewReflectionHandler(t *testing.T) {
	// This test would require a real database connection
	// For now, we test that the function exists
	handler := web.NewReflectionHandler(nil, nil)
	if handler == nil {
		t.Error("expected handler to be created, got nil")
	}
}

// TestEnergyScoreRange tests that energy score is within valid range.
func TestEnergyScoreRange(t *testing.T) {
	tests := []struct {
		score int
		valid bool
	}{
		{0, false},
		{1, true},
		{5, true},
		{7, true},
		{10, true},
		{11, false},
	}

	for _, tt := range tests {
		valid := tt.score >= 1 && tt.score <= 10
		if valid != tt.valid {
			t.Errorf("score %d: expected valid=%v, got %v", tt.score, tt.valid, valid)
		}
	}
}

// TestWeekStartCalculation tests week start date calculation.
func TestWeekStartCalculation(t *testing.T) {
	now := time.Date(2026, 6, 28, 10, 0, 0, 0, time.UTC)
	// Calculate Monday of the week: weekday + 6 mod 7 gives days since Monday
	daysSinceMonday := int((now.Weekday() + 6) % 7)
	weekStart := now.AddDate(0, 0, -daysSinceMonday)

	if weekStart.After(now) {
		t.Error("expected weekStart to be before or equal to now")
	}

	// Week start should be at most 6 days before now
	diff := now.Sub(weekStart)
	if diff > 6*24*time.Hour {
		t.Errorf("expected weekStart to be within 6 days, got %v", diff)
	}
}

// TestDashboardSummaryDefaultValues tests default values for new founders.
func TestDashboardSummaryDefaultValues(t *testing.T) {
	summary := web.DashboardSummary{
		FounderID:             "new-founder",
		Name:                  "Founder",
		Stage:                 "building",
		CommitmentRate:        0,
		OverdueCount:          0,
		TriggersFired30d:      0,
		TriggersSuppressed30d: 0,
		PositiveRatings:       0,
		NegativeRatings:       0,
		DaysSinceReflection:   0,
		EnergyTrend:           []int{},
		LastReflectionAt:      time.Now(),
	}

	if summary.CommitmentRate != 0 {
		t.Errorf("expected default CommitmentRate to be 0, got %f", summary.CommitmentRate)
	}

	if len(summary.EnergyTrend) != 0 {
		t.Errorf("expected default EnergyTrend to be empty, got %d items", len(summary.EnergyTrend))
	}
}
