package storage

import (
	"testing"
	"time"
)

func TestBuildActivityStatsFillsMissingBuckets(t *testing.T) {
	from := time.Date(2026, 6, 27, 10, 0, 0, 0, time.UTC)
	to := time.Date(2026, 6, 27, 13, 0, 0, 0, time.UTC)
	series := []string{"sync_bucket", "scan_bucket"}
	raw := map[time.Time]map[string]int{
		time.Date(2026, 6, 27, 11, 0, 0, 0, time.UTC): {
			"sync_bucket": 2,
		},
	}

	stats := BuildActivityStats(from, to, ActivityStatsBucketHour, series, raw)
	if len(stats.Points) != 3 {
		t.Fatalf("points = %d, want 3 hourly buckets", len(stats.Points))
	}
	if stats.Points[1].Counts["sync_bucket"] != 2 {
		t.Fatalf("sync_bucket count = %d, want 2", stats.Points[1].Counts["sync_bucket"])
	}
	if stats.Points[0].Counts["scan_bucket"] != 0 {
		t.Fatalf("scan_bucket count = %d, want 0 in empty bucket", stats.Points[0].Counts["scan_bucket"])
	}
}

func TestChooseActivityStatsBucket(t *testing.T) {
	from := time.Now().UTC()
	if ChooseActivityStatsBucket(from, from.Add(24*time.Hour)) != ActivityStatsBucketHour {
		t.Fatal("24h range should use hour buckets")
	}
	if ChooseActivityStatsBucket(from, from.Add(7*24*time.Hour)) != ActivityStatsBucketDay {
		t.Fatal("7d range should use day buckets")
	}
}
