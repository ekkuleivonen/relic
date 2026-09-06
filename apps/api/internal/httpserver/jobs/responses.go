package jobs

import (
	"time"

	"github.com/elei-io/pithosys/packages/storage"
)

type JobRunResponse struct {
	ID              string                `json:"id" example:"jobrun_0123456789abcdef0123456789abcdef"`
	TraceID         string                `json:"trace_id" example:"jobrun_0123456789abcdef0123456789abcdef"`
	Type            storage.JobType       `json:"type" example:"sync_bucket"`
	State           storage.JobRunState   `json:"state" example:"pending"`
	RequestedByType string                `json:"requested_by_type,omitempty" example:"api"`
	RequestedByID   string                `json:"requested_by_id,omitempty" example:"user_0123456789abcdef0123456789abcdef"`
	TargetType      string                `json:"target_type,omitempty" example:"bucket"`
	TargetID        string                `json:"target_id,omitempty" example:"bucket_0123456789abcdef0123456789abcdef"`
	Input           storage.JobRunPayload `json:"input"`
	Result          storage.JobRunPayload `json:"result"`
	Progress        storage.JobRunPayload `json:"progress"`
	Attempt         int                   `json:"attempt" example:"1"`
	MaxAttempts     int                   `json:"max_attempts" example:"3"`
	AvailableAt     time.Time             `json:"available_at"`
	LockedBy        string                `json:"locked_by,omitempty" example:"worker-1"`
	LockedAt        *time.Time            `json:"locked_at,omitempty"`
	StartedAt       *time.Time            `json:"started_at,omitempty"`
	FinishedAt      *time.Time            `json:"finished_at,omitempty"`
	ErrorMessage    string                `json:"error_message,omitempty" example:"upstream credentials rejected"`
	CreatedAt       time.Time             `json:"created_at"`
	UpdatedAt       time.Time             `json:"updated_at"`
}

func JobRunResponseFromStorage(run storage.JobRun) JobRunResponse {
	return JobRunResponse{
		ID:              run.ID,
		TraceID:         run.TraceID,
		Type:            run.Type,
		State:           run.State,
		RequestedByType: run.RequestedByType,
		RequestedByID:   run.RequestedByID,
		TargetType:      run.TargetType,
		TargetID:        run.TargetID,
		Input:           run.Input,
		Result:          run.Result,
		Progress:        run.Progress,
		Attempt:         run.Attempt,
		MaxAttempts:     run.MaxAttempts,
		AvailableAt:     run.AvailableAt,
		LockedBy:        run.LockedBy,
		LockedAt:        run.LockedAt,
		StartedAt:       run.StartedAt,
		FinishedAt:      run.FinishedAt,
		ErrorMessage:    run.ErrorMessage,
		CreatedAt:       run.CreatedAt,
		UpdatedAt:       run.UpdatedAt,
	}
}
