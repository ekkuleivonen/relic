package sync_bucket

import (
	"testing"

	"github.com/elei-io/pithosys/packages/storage"
)

func TestMergePlanCountsFromProgressUsesHigherProgressValue(t *testing.T) {
	counts := syncPlanCounts{Import: 500, Refresh: 10, Remove: 0}
	progress := storage.JobRunPayload{
		"import_objects_count":  int64(600),
		"refresh_objects_count": int64(10),
		"remove_objects_count":  int64(25),
		"objects_planned": map[string]any{
			"import":  600,
			"refresh": 10,
			"remove":  25,
		},
	}

	merged := mergePlanCountsFromProgress(counts, progress)
	if merged.Import != 600 {
		t.Fatalf("Import = %d, want 600", merged.Import)
	}
	if merged.Refresh != 10 {
		t.Fatalf("Refresh = %d, want 10", merged.Refresh)
	}
	if merged.Remove != 25 {
		t.Fatalf("Remove = %d, want 25", merged.Remove)
	}
}

func TestMergePlanCountsFromProgressKeepsLoadedCountsWhenHigher(t *testing.T) {
	counts := syncPlanCounts{Import: 700, Refresh: 0, Remove: 0}
	progress := storage.JobRunPayload{
		"import_objects_count": int64(600),
		"objects_planned": map[string]any{
			"import": 600,
		},
	}

	merged := mergePlanCountsFromProgress(counts, progress)
	if merged.Import != 700 {
		t.Fatalf("Import = %d, want 700", merged.Import)
	}
}

func TestMergePlanCountsFromProgressWithNilProgress(t *testing.T) {
	counts := syncPlanCounts{Import: 42}

	merged := mergePlanCountsFromProgress(counts, nil)
	if merged.Import != 42 {
		t.Fatalf("Import = %d, want 42", merged.Import)
	}
}
