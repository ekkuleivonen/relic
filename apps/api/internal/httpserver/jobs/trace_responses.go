package jobs

import (
	"strings"

	"github.com/elei-io/pithosys/packages/storage"
)

type JobRunDetailResponse struct {
	JobRunResponse
	TraceSummary *TraceSummaryResponse `json:"trace_summary,omitempty"`
}

type TraceSummaryResponse struct {
	TraceID        string                                 `json:"trace_id" example:"jobrun_0123456789abcdef0123456789abcdef"`
	RootJobRunID   string                                 `json:"root_job_run_id" example:"jobrun_0123456789abcdef0123456789abcdef"`
	State          storage.JobRunState                    `json:"state" example:"running"`
	Phase          string                                 `json:"phase" example:"importing"`
	ObjectsListed  int64                                  `json:"objects_listed" example:"248312"`
	ObjectsPlanned TraceObjectCountsResponse              `json:"objects_planned"`
	ObjectsApplied TraceObjectCountsResponse              `json:"objects_applied"`
	Batches        TraceBatchCountsResponse               `json:"batches"`
	StaleSeconds   int64                                  `json:"stale_seconds" example:"12"`
	JobCounts      map[string]TraceJobTypeCountsResponse  `json:"job_counts"`
}

type TraceObjectCountsResponse struct {
	Import  int64 `json:"import" example:"248312"`
	Refresh int64 `json:"refresh" example:"0"`
	Remove  int64 `json:"remove" example:"0"`
}

type TraceBatchCountsResponse struct {
	Import  TraceBatchStateResponse `json:"import"`
	Refresh TraceBatchStateResponse `json:"refresh"`
	Remove  TraceBatchStateResponse `json:"remove"`
}

type TraceBatchStateResponse struct {
	Total   int `json:"total" example:"2483"`
	Done    int `json:"done" example:"412"`
	Failed  int `json:"failed" example:"0"`
	Active  int `json:"active" example:"8"`
	Pending int `json:"pending" example:"2063"`
}

type TraceJobTypeCountsResponse struct {
	Total     int `json:"total" example:"2483"`
	Pending   int `json:"pending" example:"2063"`
	Running   int `json:"running" example:"8"`
	Succeeded int `json:"succeeded" example:"412"`
	Failed    int `json:"failed" example:"0"`
	Cancelled int `json:"cancelled" example:"0"`
}

func JobRunDetailResponseFromStorage(run storage.JobRun, summary *storage.TraceSummary) JobRunDetailResponse {
	response := JobRunDetailResponse{
		JobRunResponse: JobRunResponseFromStorage(run),
	}
	if summary != nil {
		mapped := TraceSummaryResponseFromStorage(*summary)
		response.TraceSummary = &mapped
	}

	return response
}

func TraceSummaryResponseFromStorage(summary storage.TraceSummary) TraceSummaryResponse {
	jobCounts := make(map[string]TraceJobTypeCountsResponse, len(summary.JobCounts))
	for jobType, counts := range summary.JobCounts {
		jobCounts[string(jobType)] = TraceJobTypeCountsResponse{
			Total:     counts.Total,
			Pending:   counts.Pending,
			Running:   counts.Running,
			Succeeded: counts.Succeeded,
			Failed:    counts.Failed,
			Cancelled: counts.Cancelled,
		}
	}

	return TraceSummaryResponse{
		TraceID:       summary.TraceID,
		RootJobRunID:  summary.RootJobRunID,
		State:         summary.State,
		Phase:         summary.Phase,
		ObjectsListed: summary.ObjectsListed,
		ObjectsPlanned: TraceObjectCountsResponse{
			Import:  summary.ObjectsPlanned.Import,
			Refresh: summary.ObjectsPlanned.Refresh,
			Remove:  summary.ObjectsPlanned.Remove,
		},
		ObjectsApplied: TraceObjectCountsResponse{
			Import:  summary.ObjectsApplied.Import,
			Refresh: summary.ObjectsApplied.Refresh,
			Remove:  summary.ObjectsApplied.Remove,
		},
		Batches: TraceBatchCountsResponse{
			Import:  traceBatchStateResponseFromStorage(summary.Batches.Import),
			Refresh: traceBatchStateResponseFromStorage(summary.Batches.Refresh),
			Remove:  traceBatchStateResponseFromStorage(summary.Batches.Remove),
		},
		StaleSeconds: summary.StaleSeconds,
		JobCounts:    jobCounts,
	}
}

func traceBatchStateResponseFromStorage(state storage.TraceBatchState) TraceBatchStateResponse {
	return TraceBatchStateResponse{
		Total:   state.Total,
		Done:    state.Done,
		Failed:  state.Failed,
		Active:  state.Active,
		Pending: state.Pending,
	}
}

func includesTraceSummary(include string) bool {
	for _, part := range strings.Split(include, ",") {
		if strings.TrimSpace(part) == "trace_summary" {
			return true
		}
	}

	return false
}
