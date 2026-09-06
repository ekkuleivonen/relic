package jobs

import (
	"testing"

	"github.com/elei-io/pithosys/packages/storage"
)

func TestIncludesTraceSummary(t *testing.T) {
	if !includesTraceSummary("trace_summary") {
		t.Fatal("includesTraceSummary(trace_summary) = false, want true")
	}
	if !includesTraceSummary("trace_summary,other") {
		t.Fatal("includesTraceSummary(trace_summary,other) = false, want true")
	}
	if includesTraceSummary("") {
		t.Fatal("includesTraceSummary('') = true, want false")
	}
	if includesTraceSummary("other") {
		t.Fatal("includesTraceSummary(other) = true, want false")
	}
}

func TestTraceSummaryResponseFromStorage(t *testing.T) {
	summary := storage.TraceSummary{
		TraceID:       "jobrun_root",
		RootJobRunID:  "jobrun_root",
		State:         storage.JobRunStateRunning,
		Phase:         "importing",
		ObjectsListed: 1000,
		ObjectsPlanned: storage.TraceObjectCounts{
			Import: 1000,
		},
		ObjectsApplied: storage.TraceObjectCounts{
			Import: 500,
		},
		Batches: storage.TraceBatchCounts{
			Import: storage.TraceBatchState{
				Total:   2,
				Done:    1,
				Pending: 1,
			},
		},
		StaleSeconds: 12,
		JobCounts: map[storage.JobType]storage.TraceJobTypeCounts{
			storage.JobTypeImportObjects: {
				Total:   2,
				Pending: 1,
				Succeeded: 1,
			},
		},
	}

	response := TraceSummaryResponseFromStorage(summary)
	if response.TraceID != summary.TraceID {
		t.Fatalf("trace_id = %q, want %q", response.TraceID, summary.TraceID)
	}
	if response.ObjectsApplied.Import != 500 {
		t.Fatalf("objects_applied.import = %d, want 500", response.ObjectsApplied.Import)
	}
	if response.Batches.Import.Done != 1 {
		t.Fatalf("batches.import.done = %d, want 1", response.Batches.Import.Done)
	}
	if response.JobCounts["import_objects"].Total != 2 {
		t.Fatalf("job_counts.import_objects.total = %d, want 2", response.JobCounts["import_objects"].Total)
	}
}
