package scheduler

import (
	"testing"
	"time"
)

func TestDecideScanEnqueuesWhenDueAndNoActiveRun(t *testing.T) {
	now := time.Date(2026, 6, 28, 12, 0, 0, 0, time.UTC)

	decision := DecideScan(nil, now, false, 24*time.Hour)
	if decision != ScanDecisionEnqueue {
		t.Fatalf("DecideScan() = %q, want %q", decision, ScanDecisionEnqueue)
	}
}

func TestDecideScanSkipsWhenActiveRunExists(t *testing.T) {
	now := time.Date(2026, 6, 28, 12, 0, 0, 0, time.UTC)

	decision := DecideScan(nil, now, true, 24*time.Hour)
	if decision != ScanDecisionSkipActive {
		t.Fatalf("DecideScan() = %q, want %q", decision, ScanDecisionSkipActive)
	}
}

func TestDecideScanSkipsWhenNotDue(t *testing.T) {
	lastFinished := time.Date(2026, 6, 28, 0, 0, 0, 0, time.UTC)
	now := lastFinished.Add(12 * time.Hour)

	decision := DecideScan(&lastFinished, now, false, 24*time.Hour)
	if decision != ScanDecisionSkipNotDue {
		t.Fatalf("DecideScan() = %q, want %q", decision, ScanDecisionSkipNotDue)
	}
}
