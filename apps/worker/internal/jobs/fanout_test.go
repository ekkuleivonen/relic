package jobs

import (
	"testing"

	"github.com/ekkuleivonen/relic/packages/storage"
)

func TestFanOutResultSetsAwaitChildrenWhenChildJobsExist(t *testing.T) {
	result := FanOutResult(map[string][]string{
		"import_objects": {"jobrun_child"},
	}, storage.JobRunPayload{
		"objects_seen": int64(2),
	})

	if !AwaitsChildren(result) {
		t.Fatal("AwaitsChildren() = false, want true")
	}
	if !result[ResultKeyAwaitChildren].(bool) {
		t.Fatal("await_children = false, want true")
	}
}

func TestFanOutResultOmitsAwaitChildrenWithoutChildJobs(t *testing.T) {
	result := FanOutResult(map[string][]string{
		"import_objects": {},
	}, storage.JobRunPayload{
		"objects_seen": int64(0),
	})

	if AwaitsChildren(result) {
		t.Fatal("AwaitsChildren() = true, want false")
	}
}

func TestFanOutProgressMapsPlannedFields(t *testing.T) {
	progress := FanOutProgress(storage.JobRunPayload{
		"objects_seen":          int64(10),
		"import_objects_count":  8,
		"refresh_objects_count": 1,
		"remove_objects_count":  1,
		ResultKeyChildJobIDs: map[string]any{
			"import_objects":  []any{"jobrun_1", "jobrun_2"},
			"refresh_objects": []any{"jobrun_3"},
			"remove_objects":  []any{"jobrun_4"},
		},
	})

	if progress["phase"] != "applying" {
		t.Fatalf("phase = %#v, want applying", progress["phase"])
	}
	if progress["objects_listed"] != int64(10) {
		t.Fatalf("objects_listed = %#v, want 10", progress["objects_listed"])
	}
	planned, ok := progress["objects_planned"].(map[string]any)
	if !ok {
		t.Fatalf("objects_planned = %#v, want map", progress["objects_planned"])
	}
	if planned["import"] != 8 {
		t.Fatalf("objects_planned.import = %#v, want 8", planned["import"])
	}
	batches, ok := progress["batches"].(map[string]any)
	if !ok {
		t.Fatalf("batches = %#v, want map", progress["batches"])
	}
	importBatches, ok := batches["import"].(map[string]any)
	if !ok || importBatches["total"] != 2 {
		t.Fatalf("batches.import = %#v, want total 2", batches["import"])
	}
}

func TestFanOutProgressUsesAwaitingSyncForScanEscalation(t *testing.T) {
	progress := FanOutProgress(storage.JobRunPayload{
		ResultKeyChildJobIDs: map[string]any{
			"sync_bucket": []any{"jobrun_sync"},
		},
	})

	if progress["phase"] != "awaiting_sync" {
		t.Fatalf("phase = %#v, want awaiting_sync", progress["phase"])
	}
}
