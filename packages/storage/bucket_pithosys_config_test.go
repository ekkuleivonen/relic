package storage

import (
	"testing"
	"time"
)

func TestBucketPithosysConfigScanEnabledByDefault(t *testing.T) {
	config := BucketPithosysConfig{}

	if !config.ScanEnabled() {
		t.Fatal("ScanEnabled() = false, want true for empty config")
	}
}

func TestBucketPithosysConfigScanExplicitlyDisabled(t *testing.T) {
	config := BucketPithosysConfig{
		Scan: BucketScanConfig{Enabled: BoolPtr(false)},
	}

	if config.ScanEnabled() {
		t.Fatal("ScanEnabled() = true, want false when explicitly disabled")
	}
}

func TestBucketPithosysConfigScanIntervalDefaultsTo24h(t *testing.T) {
	config := BucketPithosysConfig{}

	got := config.ScanInterval(DefaultScanInterval)
	if got != 24*time.Hour {
		t.Fatalf("ScanInterval() = %v, want 24h", got)
	}
}

func TestBucketPithosysConfigScanIntervalParsesConfiguredValue(t *testing.T) {
	config := BucketPithosysConfig{
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

func TestBucketPithosysConfigScanDueWhenNeverScanned(t *testing.T) {
	config := BucketPithosysConfig{}
	now := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)

	if !config.ScanDue(nil, now, DefaultScanInterval) {
		t.Fatal("ScanDue() = false, want true when no prior scan")
	}
}

func TestBucketPithosysConfigScanNotDueBeforeIntervalElapses(t *testing.T) {
	config := BucketPithosysConfig{
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

func TestBucketPithosysConfigScanDueAfterIntervalElapses(t *testing.T) {
	config := BucketPithosysConfig{
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

func TestBucketPithosysConfigScanNotDueWhenDisabled(t *testing.T) {
	config := BucketPithosysConfig{
		Scan: BucketScanConfig{Enabled: BoolPtr(false)},
	}
	now := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)

	if config.ScanDue(nil, now, DefaultScanInterval) {
		t.Fatal("ScanDue() = true, want false when scan disabled")
	}
}

func TestDefaultBucketPithosysConfig(t *testing.T) {
	config := DefaultBucketPithosysConfig()

	if !config.ScanEnabled() {
		t.Fatal("ScanEnabled() = false, want true")
	}
	if config.Scan.Interval != "24h" {
		t.Fatalf("interval = %q, want 24h", config.Scan.Interval)
	}
}
