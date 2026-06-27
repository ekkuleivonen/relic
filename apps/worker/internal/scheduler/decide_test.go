package scheduler

import (
	"testing"
	"time"

	"github.com/ekkuleivonen/relic/packages/storage"
)

func TestDecideScanEnqueuesWhenDueAndNoActiveRun(t *testing.T) {
	bucket := storage.Bucket{
		RelicConfig: storage.BucketRelicConfig{
			Scan: storage.BucketScanConfig{Enabled: storage.BoolPtr(true), Interval: "24h"},
		},
	}
	now := time.Date(2026, 6, 28, 12, 0, 0, 0, time.UTC)

	decision := DecideScan(bucket, nil, now, false, storage.DefaultScanInterval)
	if decision != ScanDecisionEnqueue {
		t.Fatalf("DecideScan() = %q, want %q", decision, ScanDecisionEnqueue)
	}
}

func TestDecideScanSkipsWhenDisabled(t *testing.T) {
	bucket := storage.Bucket{
		RelicConfig: storage.BucketRelicConfig{
			Scan: storage.BucketScanConfig{Enabled: storage.BoolPtr(false)},
		},
	}
	now := time.Date(2026, 6, 28, 12, 0, 0, 0, time.UTC)

	decision := DecideScan(bucket, nil, now, false, storage.DefaultScanInterval)
	if decision != ScanDecisionSkipDisabled {
		t.Fatalf("DecideScan() = %q, want %q", decision, ScanDecisionSkipDisabled)
	}
}

func TestDecideScanEnqueuesWithDefaultRelicConfig(t *testing.T) {
	bucket := storage.Bucket{}
	now := time.Date(2026, 6, 28, 12, 0, 0, 0, time.UTC)

	decision := DecideScan(bucket, nil, now, false, storage.DefaultScanInterval)
	if decision != ScanDecisionEnqueue {
		t.Fatalf("DecideScan() = %q, want %q", decision, ScanDecisionEnqueue)
	}
}

func TestDecideScanSkipsWhenActiveRunExists(t *testing.T) {
	bucket := storage.Bucket{
		RelicConfig: storage.BucketRelicConfig{
			Scan: storage.BucketScanConfig{Enabled: storage.BoolPtr(true)},
		},
	}
	now := time.Date(2026, 6, 28, 12, 0, 0, 0, time.UTC)

	decision := DecideScan(bucket, nil, now, true, storage.DefaultScanInterval)
	if decision != ScanDecisionSkipActive {
		t.Fatalf("DecideScan() = %q, want %q", decision, ScanDecisionSkipActive)
	}
}

func TestDecideScanSkipsWhenNotDue(t *testing.T) {
	bucket := storage.Bucket{
		RelicConfig: storage.BucketRelicConfig{
			Scan: storage.BucketScanConfig{Enabled: storage.BoolPtr(true), Interval: "24h"},
		},
	}
	lastFinished := time.Date(2026, 6, 28, 0, 0, 0, 0, time.UTC)
	now := lastFinished.Add(12 * time.Hour)

	decision := DecideScan(bucket, &lastFinished, now, false, storage.DefaultScanInterval)
	if decision != ScanDecisionSkipNotDue {
		t.Fatalf("DecideScan() = %q, want %q", decision, ScanDecisionSkipNotDue)
	}
}
