package jobs

import (
	"context"
	"errors"
	"net/http"
	"strings"

	"github.com/danielgtaylor/huma/v2"
	"github.com/elei-io/pithosys/apps/api/internal/httpserver/deps"
	"github.com/elei-io/pithosys/apps/api/internal/httpserver/middleware"
	observabilityhttp "github.com/elei-io/pithosys/apps/api/internal/httpserver/observability"
	"github.com/elei-io/pithosys/packages/storage"
)

func Register(api huma.API, dependencies deps.Dependencies, basePath string) {
	huma.Register(api, huma.Operation{
		OperationID: "list-job-runs",
		Method:      http.MethodGet,
		Path:        basePath + "/job-runs",
		Summary:     "List job runs",
		Tags:        []string{"Jobs"},
	}, func(ctx context.Context, input *listJobRunsInput) (*listJobRunsOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("job dependencies are not configured")
		}

		params, err := listJobRunsParamsFromInput(input)
		if err != nil {
			return nil, huma.Error422UnprocessableEntity(err.Error())
		}

		runs, err := dependencies.Storage.JobRuns().ListJobRuns(ctx, params)
		if err != nil {
			return nil, err
		}

		total, err := dependencies.Storage.JobRuns().CountJobRuns(ctx, params)
		if err != nil {
			return nil, err
		}

		limit := params.Limit
		if limit <= 0 {
			limit = 100
		}

		body := listJobRunsBody{
			JobRuns: make([]jobRunResponse, 0, len(runs)),
			Total:   total,
			Limit:   limit,
			Offset:  params.Offset,
		}
		for _, run := range runs {
			body.JobRuns = append(body.JobRuns, jobRunResponseFromStorage(run))
		}

		return &listJobRunsOutput{Body: body}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "get-job-run-stats",
		Method:      http.MethodGet,
		Path:        basePath + "/job-runs/stats",
		Summary:     "Get job run activity stats",
		Tags:        []string{"Observability"},
	}, func(ctx context.Context, input *jobRunStatsInput) (*jobRunStatsOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("job dependencies are not configured")
		}

		params, err := listJobRunsParamsFromStatsInput(input)
		if err != nil {
			return nil, huma.Error422UnprocessableEntity(err.Error())
		}
		if params.CreatedAfter == nil || params.CreatedBefore == nil {
			return nil, huma.Error422UnprocessableEntity("created_after and created_before are required")
		}

		stats, err := dependencies.Storage.JobRuns().JobRunActivityStats(ctx, storage.JobRunActivityStatsParams{
			ListJobRunsParams: params,
			Series:            parseJobRunTypeStrings(input.Types, input.Type),
		})
		if err != nil {
			return nil, huma.Error422UnprocessableEntity(err.Error())
		}

		return &jobRunStatsOutput{Body: observabilityhttp.ActivityStatsResponseFromStorage(stats)}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "get-job-run",
		Method:      http.MethodGet,
		Path:        basePath + "/job-runs/{id}",
		Summary:     "Get job run",
		Tags:        []string{"Jobs"},
	}, func(ctx context.Context, input *getJobRunInput) (*jobRunOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("job dependencies are not configured")
		}

		run, err := dependencies.Storage.JobRuns().GetJobRun(ctx, input.ID)
		if errors.Is(err, storage.ErrNotFound) {
			return nil, huma.Error404NotFound("job run not found")
		}
		if err != nil {
			return nil, err
		}

		var summary *storage.TraceSummary
		if includesTraceSummary(input.Include) {
			if run.TraceID == "" {
				return nil, huma.Error500InternalServerError("job run is missing trace_id")
			}
			traceSummary, err := dependencies.Storage.JobRuns().SummarizeTrace(ctx, run.TraceID)
			if err != nil {
				return nil, err
			}
			summary = &traceSummary
		}

		return &jobRunOutput{Body: JobRunDetailResponseFromStorage(run, summary)}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID:   "create-detect-duplicates-job",
		Method:        http.MethodPost,
		Path:          basePath + "/detect-duplicates",
		Summary:       "Start duplicate detection",
		Tags:          []string{"Jobs"},
		DefaultStatus: http.StatusAccepted,
	}, func(ctx context.Context, input *createDetectDuplicatesInput) (*createDetectDuplicatesOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("job dependencies are not configured")
		}

		payload := storage.JobRunPayload{}
		if input.Body.Scope != nil {
			payload["scope"] = input.Body.Scope
		}

		requestedBy := middleware.RequestedByFromContext(ctx, dependencies)
		run, err := dependencies.Storage.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
			Type:            storage.JobTypeDetectDuplicates,
			RequestedByType: requestedBy.Type,
			RequestedByID:   requestedBy.ID,
			TargetType:      "catalog",
			TargetID:        "catalog",
			Input:           payload,
		})
		if err != nil {
			return nil, err
		}

		return &createDetectDuplicatesOutput{Body: jobRunResponseFromStorage(run)}, nil
	})
}

type listJobRunsInput struct {
	Type            string `query:"type" example:"sync_bucket"`
	Types           string `query:"types" example:"sync_bucket,scan_bucket"`
	State           string `query:"state" example:"pending"`
	TraceID         string `query:"trace_id" example:"jobrun_0123456789abcdef0123456789abcdef"`
	RequestedByType string `query:"requested_by_type" example:"job"`
	RequestedByID   string `query:"requested_by_id" example:"jobrun_0123456789abcdef0123456789abcdef"`
	TargetType      string `query:"target_type" example:"bucket"`
	TargetID        string `query:"target_id" example:"bucket_0123456789abcdef0123456789abcdef"`
	CreatedAfter    string `query:"created_after" example:"2026-06-27T00:00:00Z"`
	CreatedBefore   string `query:"created_before" example:"2026-06-28T00:00:00Z"`
	Limit           int    `query:"limit" example:"100"`
	Offset          int    `query:"offset" example:"0"`
}

type jobRunStatsInput struct {
	Type            string `query:"type" example:"sync_bucket"`
	Types           string `query:"types" example:"sync_bucket,scan_bucket"`
	State           string `query:"state" example:"pending"`
	RequestedByType string `query:"requested_by_type" example:"job"`
	RequestedByID   string `query:"requested_by_id" example:"jobrun_0123456789abcdef0123456789abcdef"`
	TargetType      string `query:"target_type" example:"bucket"`
	TargetID        string `query:"target_id" example:"bucket_0123456789abcdef0123456789abcdef"`
	CreatedAfter    string `query:"created_after" example:"2026-06-27T00:00:00Z"`
	CreatedBefore   string `query:"created_before" example:"2026-06-28T00:00:00Z"`
}

type getJobRunInput struct {
	ID      string `path:"id" example:"jobrun_0123456789abcdef0123456789abcdef"`
	Include string `query:"include" example:"trace_summary"`
}

type createDetectDuplicatesInput struct {
	Body createDetectDuplicatesBody
}

type createDetectDuplicatesBody struct {
	Scope map[string]any `json:"scope,omitempty"`
}

type createDetectDuplicatesOutput struct {
	Body jobRunResponse
}

type jobRunOutput struct {
	Body JobRunDetailResponse
}

type listJobRunsOutput struct {
	Body listJobRunsBody
}

type listJobRunsBody struct {
	JobRuns []jobRunResponse `json:"job_runs"`
	Total   int              `json:"total"`
	Limit   int              `json:"limit"`
	Offset  int              `json:"offset"`
}

type jobRunStatsOutput struct {
	Body observabilityhttp.ActivityStatsResponse
}

type jobRunResponse = JobRunResponse

func jobRunResponseFromStorage(run storage.JobRun) jobRunResponse {
	return JobRunResponseFromStorage(run)
}

func parseJobRunTypes(raw string) []storage.JobType {
	if strings.TrimSpace(raw) == "" {
		return nil
	}

	parts := strings.Split(raw, ",")
	types := make([]storage.JobType, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part != "" {
			types = append(types, storage.JobType(part))
		}
	}

	return types
}

func parseJobRunTypeStrings(typesRaw, typeRaw string) []string {
	types := parseJobRunTypes(typesRaw)
	if len(types) > 0 {
		out := make([]string, 0, len(types))
		for _, jobType := range types {
			out = append(out, string(jobType))
		}

		return out
	}

	if strings.TrimSpace(typeRaw) != "" {
		return []string{typeRaw}
	}

	return nil
}

func listJobRunsParamsFromInput(input *listJobRunsInput) (storage.ListJobRunsParams, error) {
	createdAfter, err := observabilityhttp.ParseOptionalTime(input.CreatedAfter)
	if err != nil {
		return storage.ListJobRunsParams{}, err
	}
	createdBefore, err := observabilityhttp.ParseOptionalTime(input.CreatedBefore)
	if err != nil {
		return storage.ListJobRunsParams{}, err
	}

	return storage.ListJobRunsParams{
		Type:            storage.JobType(input.Type),
		Types:           parseJobRunTypes(input.Types),
		State:           storage.JobRunState(input.State),
		TraceID:         input.TraceID,
		RequestedByType: input.RequestedByType,
		RequestedByID:   input.RequestedByID,
		TargetType:      input.TargetType,
		TargetID:        input.TargetID,
		CreatedAfter:    createdAfter,
		CreatedBefore:   createdBefore,
		Limit:           input.Limit,
		Offset:          input.Offset,
	}, nil
}

func listJobRunsParamsFromStatsInput(input *jobRunStatsInput) (storage.ListJobRunsParams, error) {
	createdAfter, err := observabilityhttp.ParseOptionalTime(input.CreatedAfter)
	if err != nil {
		return storage.ListJobRunsParams{}, err
	}
	createdBefore, err := observabilityhttp.ParseOptionalTime(input.CreatedBefore)
	if err != nil {
		return storage.ListJobRunsParams{}, err
	}

	return storage.ListJobRunsParams{
		Type:            storage.JobType(input.Type),
		Types:           parseJobRunTypes(input.Types),
		State:           storage.JobRunState(input.State),
		RequestedByType: input.RequestedByType,
		RequestedByID:   input.RequestedByID,
		TargetType:      input.TargetType,
		TargetID:        input.TargetID,
		CreatedAfter:    createdAfter,
		CreatedBefore:   createdBefore,
	}, nil
}
