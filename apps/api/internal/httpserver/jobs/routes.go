package jobs

import (
	"context"
	"errors"
	"net/http"

	"github.com/danielgtaylor/huma/v2"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/deps"
	"github.com/ekkuleivonen/relic/packages/storage"
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

		runs, err := dependencies.Storage.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
			Type:       storage.JobType(input.Type),
			State:      storage.JobRunState(input.State),
			TargetType: input.TargetType,
			TargetID:   input.TargetID,
			Limit:      input.Limit,
			Offset:     input.Offset,
		})
		if err != nil {
			return nil, err
		}

		body := listJobRunsBody{JobRuns: make([]jobRunResponse, 0, len(runs))}
		for _, run := range runs {
			body.JobRuns = append(body.JobRuns, jobRunResponseFromStorage(run))
		}

		return &listJobRunsOutput{Body: body}, nil
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

		return &jobRunOutput{Body: jobRunResponseFromStorage(run)}, nil
	})
}

type listJobRunsInput struct {
	Type       string `query:"type" example:"sync_bucket"`
	State      string `query:"state" example:"pending"`
	TargetType string `query:"target_type" example:"bucket"`
	TargetID   string `query:"target_id" example:"bucket_0123456789abcdef0123456789abcdef"`
	Limit      int    `query:"limit" example:"100"`
	Offset     int    `query:"offset" example:"0"`
}

type getJobRunInput struct {
	ID string `path:"id" example:"jobrun_0123456789abcdef0123456789abcdef"`
}

type jobRunOutput struct {
	Body jobRunResponse
}

type listJobRunsOutput struct {
	Body listJobRunsBody
}

type listJobRunsBody struct {
	JobRuns []jobRunResponse `json:"job_runs"`
}

type jobRunResponse = JobRunResponse

func jobRunResponseFromStorage(run storage.JobRun) jobRunResponse {
	return JobRunResponseFromStorage(run)
}
