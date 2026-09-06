package sync_bucket

import (
	"context"

	"github.com/elei-io/pithosys/apps/worker/internal/jobs"
	"github.com/elei-io/pithosys/packages/storage"
)

type syncExecutionState struct {
	planCounts  syncPlanCounts
	childJobIDs map[string][]string
}

func newSyncExecutionState() *syncExecutionState {
	return &syncExecutionState{
		childJobIDs: map[string][]string{
			string(storage.JobTypeImportObjects):  {},
			string(storage.JobTypeRefreshObjects): {},
			string(storage.JobTypeRemoveObjects):  {},
		},
	}
}

func (h *Handler) loadSyncExecutionState(ctx context.Context, run storage.JobRun) (*syncExecutionState, error) {
	state := newSyncExecutionState()

	children, err := h.store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		RequestedByType: "job",
		RequestedByID:   run.ID,
		Limit:           10000,
	})
	if err != nil {
		return nil, err
	}

	for _, child := range children {
		state.childJobIDs[string(child.Type)] = append(state.childJobIDs[string(child.Type)], child.ID)
		switch child.Type {
		case storage.JobTypeImportObjects:
			state.planCounts.Import += mutationObjectCount(child.Input)
		case storage.JobTypeRefreshObjects:
			state.planCounts.Refresh += mutationObjectCount(child.Input)
		case storage.JobTypeRemoveObjects:
			state.planCounts.Remove += mutationObjectCount(child.Input)
		}
	}

	state.planCounts = mergePlanCountsFromProgress(state.planCounts, run.Progress)

	return state, nil
}

func mergePlanCountsFromProgress(counts syncPlanCounts, progress storage.JobRunPayload) syncPlanCounts {
	return syncPlanCounts{
		Import:  max(counts.Import, plannedCountFromProgress(progress, "import")),
		Refresh: max(counts.Refresh, plannedCountFromProgress(progress, "refresh")),
		Remove:  max(counts.Remove, plannedCountFromProgress(progress, "remove")),
	}
}

func plannedCountFromProgress(progress storage.JobRunPayload, kind string) int {
	if progress == nil {
		return 0
	}

	var topLevelKey string
	switch kind {
	case "import":
		topLevelKey = "import_objects_count"
	case "refresh":
		topLevelKey = "refresh_objects_count"
	case "remove":
		topLevelKey = "remove_objects_count"
	default:
		return 0
	}

	count := int(storage.PayloadInt64(progress, topLevelKey))
	if planned, ok := progress["objects_planned"].(map[string]any); ok && planned != nil {
		if raw, ok := planned[kind]; ok {
			switch typed := raw.(type) {
			case float64:
				count = max(count, int(typed))
			case int:
				count = max(count, typed)
			case int64:
				count = max(count, int(typed))
			}
		}
	}

	return count
}

func (state *syncExecutionState) record(jobType storage.JobType, objectCount int, jobIDs []string) {
	if len(jobIDs) == 0 {
		return
	}

	key := string(jobType)
	state.childJobIDs[key] = append(state.childJobIDs[key], jobIDs...)
	switch jobType {
	case storage.JobTypeImportObjects:
		state.planCounts = state.planCounts.add(objectCount, 0, 0)
	case storage.JobTypeRefreshObjects:
		state.planCounts = state.planCounts.add(0, objectCount, 0)
	case storage.JobTypeRemoveObjects:
		state.planCounts = state.planCounts.add(0, 0, objectCount)
	}
}

func (state *syncExecutionState) fanOutResult(base storage.JobRunPayload) storage.JobRunPayload {
	result := base
	if result == nil {
		result = storage.JobRunPayload{}
	}

	result["import_objects_count"] = state.planCounts.Import
	result["refresh_objects_count"] = state.planCounts.Refresh
	result["remove_objects_count"] = state.planCounts.Remove

	return jobs.FanOutResult(state.childJobIDs, result)
}

func mutationObjectCount(input storage.JobRunPayload) int {
	raw, ok := input["objects"]
	if !ok || raw == nil {
		return 0
	}
	switch typed := raw.(type) {
	case []any:
		return len(typed)
	default:
		return 0
	}
}
