package scan_bucket

import (
	"testing"
	"time"
)

func TestScanBudgetStopsWhenMaxObjectsReached(t *testing.T) {
	now := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)
	clock := func() time.Time { return now }
	budget := NewScanBudget(ScanBudgetConfig{MaxObjectsListed: 2}, now, clock)

	if !budget.Allow(1) {
		t.Fatal("Allow(1) = false, want true")
	}
	budget.Record(1)
	if !budget.Allow(1) {
		t.Fatal("Allow(1) after one object = false, want true")
	}
	budget.Record(1)
	if budget.Allow(1) {
		t.Fatal("Allow(1) after budget exhausted = true, want false")
	}
}

func TestScanBudgetUsesDefaultsWhenUnset(t *testing.T) {
	now := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)
	clock := func() time.Time { return now }
	budget := NewScanBudget(ScanBudgetConfig{}, now, clock)
	if !budget.Allow(1) {
		t.Fatal("Allow(1) with defaults = false, want true")
	}
}

func TestScanBudgetStopsWhenDeadlineReached(t *testing.T) {
	start := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)
	afterDeadline := start.Add(2 * time.Minute)
	budget := NewScanBudget(ScanBudgetConfig{MaxDuration: time.Minute}, start, func() time.Time { return start })

	if !budget.Allow(1) {
		t.Fatal("Allow(1) before deadline = false, want true")
	}

	budget = NewScanBudget(ScanBudgetConfig{MaxDuration: time.Minute}, start, func() time.Time { return afterDeadline })
	if budget.Allow(1) {
		t.Fatal("Allow(1) after deadline = true, want false")
	}
}

func TestScanBudgetAllowZeroChecksDeadline(t *testing.T) {
	start := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)
	afterDeadline := start.Add(2 * time.Minute)
	budget := NewScanBudget(ScanBudgetConfig{MaxDuration: time.Minute}, start, func() time.Time { return afterDeadline })

	if budget.Allow(0) {
		t.Fatal("Allow(0) after deadline = true, want false")
	}
}

func TestScanBudgetAllowZeroBeforeDeadline(t *testing.T) {
	start := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)
	budget := NewScanBudget(ScanBudgetConfig{MaxDuration: time.Minute}, start, func() time.Time { return start })

	if !budget.Allow(0) {
		t.Fatal("Allow(0) before deadline = false, want true")
	}
}
