package storage

import (
	"testing"
	"time"
)

func TestBucketRelicConfigScanEnabledByDefault(t *testing.T) {
	config := BucketRelicConfig{}

	if !config.ScanEnabled() {
		t.Fatal("ScanEnabled() = false, want true for empty config")
	}
}

func TestBucketRelicConfigScanExplicitlyDisabled(t *testing.T) {
	config := BucketRelicConfig{
		Scan: BucketScanConfig{Enabled: BoolPtr(false)},
	}

	if config.ScanEnabled() {
		t.Fatal("ScanEnabled() = true, want false when explicitly disabled")
	}
}

func TestBucketRelicConfigScanIntervalDefaultsTo24h(t *testing.T) {
	config := BucketRelicConfig{}

	got := config.ScanInterval(DefaultScanInterval)
	if got != 24*time.Hour {
		t.Fatalf("ScanInterval() = %v, want 24h", got)
	}
}

func TestBucketRelicConfigScanIntervalParsesConfiguredValue(t *testing.T) {
	config := BucketRelicConfig{
		Scan: BucketScanConfig{
			Enabled:  BoolPtr(true),
			Interval: "6h",
		},
	}

	got := config.ScanInterval(DefaultScanInterval)
	if got != 6*time.Hour {
		t.Fatalf("ScanInterval() = %v, want 6h", got)
	}
}

func TestBucketRelicConfigScanDueWhenNeverScanned(t *testing.T) {
	config := BucketRelicConfig{}
	now := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)

	if !config.ScanDue(nil, now, DefaultScanInterval) {
		t.Fatal("ScanDue() = false, want true when no prior scan")
	}
}

func TestBucketRelicConfigScanNotDueBeforeIntervalElapses(t *testing.T) {
	config := BucketRelicConfig{
		Scan: BucketScanConfig{
			Enabled:  BoolPtr(true),
			Interval: "24h",
		},
	}
	lastFinished := time.Date(2026, 6, 27, 0, 0, 0, 0, time.UTC)
	now := lastFinished.Add(12 * time.Hour)

	if config.ScanDue(&lastFinished, now, DefaultScanInterval) {
		t.Fatal("ScanDue() = true, want false before interval elapsed")
	}
}

func TestBucketRelicConfigScanDueAfterIntervalElapses(t *testing.T) {
	config := BucketRelicConfig{
		Scan: BucketScanConfig{
			Enabled:  BoolPtr(true),
			Interval: "24h",
		},
	}
	lastFinished := time.Date(2026, 6, 26, 12, 0, 0, 0, time.UTC)
	now := lastFinished.Add(24 * time.Hour)

	if !config.ScanDue(&lastFinished, now, DefaultScanInterval) {
		t.Fatal("ScanDue() = false, want true after interval elapsed")
	}
}

func TestBucketRelicConfigScanNotDueWhenDisabled(t *testing.T) {
	config := BucketRelicConfig{
		Scan: BucketScanConfig{Enabled: BoolPtr(false)},
	}
	now := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)

	if config.ScanDue(nil, now, DefaultScanInterval) {
		t.Fatal("ScanDue() = true, want false when scan disabled")
	}
}

func TestDefaultBucketRelicConfig(t *testing.T) {
	config := DefaultBucketRelicConfig()

	if !config.ScanEnabled() {
		t.Fatal("ScanEnabled() = false, want true")
	}
	if config.Scan.Interval != "24h" {
		t.Fatalf("interval = %q, want 24h", config.Scan.Interval)
	}
}
