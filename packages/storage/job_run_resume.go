package storage

import (
	"context"
	"fmt"
)

const DefaultSyncBucketMaxAttempts = 5

type FindResumableSyncJobRunParams struct {
	TargetType  string
	TargetID    string
	ScopePrefix string
}

func (s *JobRunStore) FindResumableSyncJobRun(ctx context.Context, params FindResumableSyncJobRunParams) (JobRun, error) {
	if params.TargetType == "" {
		return JobRun{}, fmt.Errorf("find resumable sync job run: target type is required")
	}
	if params.TargetID == "" {
		return JobRun{}, fmt.Errorf("find resumable sync job run: target id is required")
	}

	run, err := scanJobRun(s.runner.QueryRow(ctx, `
		SELECT `+jobRunColumns+`
		FROM job_runs AS candidate
		WHERE candidate.type = $1
			AND candidate.id = candidate.trace_id
			AND candidate.target_type IS NOT DISTINCT FROM $2
			AND candidate.target_id IS NOT DISTINCT FROM $3
			AND candidate.state IN ('failed', 'cancelled')
			AND NOT EXISTS (
				SELECT 1
				FROM job_runs AS newer
				WHERE newer.type = $1
					AND newer.id = newer.trace_id
					AND newer.target_type IS NOT DISTINCT FROM $2
					AND newer.target_id IS NOT DISTINCT FROM $3
					AND newer.created_at > candidate.created_at
			)
		ORDER BY candidate.created_at DESC, candidate.id DESC
		LIMIT 1
	`, JobTypeSyncBucket, params.TargetType, params.TargetID))
	if err != nil {
		return JobRun{}, err
	}

	if !IsResumableSyncJobRun(run, params.ScopePrefix) {
		return JobRun{}, ErrNotFound
	}

	return run, nil
}

func IsResumableSyncJobRun(run JobRun, scopePrefix string) bool {
	if run.Type != JobTypeSyncBucket || !IsRootJob(run) {
		return false
	}
	if run.State != JobRunStateFailed && run.State != JobRunStateCancelled {
		return false
	}
	if !syncJobInputMatchesScope(run.Input, scopePrefix) {
		return false
	}
	if PayloadBool(run.Progress, "listing_complete") {
		return run.State == JobRunStateFailed || run.State == JobRunStateCancelled
	}

	return hasListingCheckpointProgress(run.Progress)
}

func hasListingCheckpointProgress(progress JobRunPayload) bool {
	if progress == nil {
		return false
	}
	if PayloadInt64(progress, "objects_listed") > 0 {
		return true
	}

	raw, ok := progress["listing_checkpoint"].(map[string]any)
	if !ok || raw == nil {
		return false
	}
	if PayloadInt64(raw, "objects_listed") > 0 {
		return true
	}
	if token, ok := raw["continuation_token"].(string); ok && token != "" {
		return true
	}
	if marker, ok := raw["marker"].(string); ok && marker != "" {
		return true
	}

	return false
}

func syncJobInputMatchesScope(input JobRunPayload, scopePrefix string) bool {
	if input == nil {
		return scopePrefix == ""
	}
	if _, hasPartition := input["partition"]; hasPartition {
		return false
	}

	jobScopePrefix := ""
	if value, ok := input["scope_prefix"].(string); ok {
		jobScopePrefix = value
	} else if value, ok := input["prefix"].(string); ok {
		jobScopePrefix = value
	}

	return jobScopePrefix == scopePrefix
}

func (s *JobRunStore) ResumeJobRun(ctx context.Context, id string) (JobRun, error) {
	if id == "" {
		return JobRun{}, fmt.Errorf("resume job run: id is required")
	}

	return scanJobRun(s.runner.QueryRow(ctx, `
		UPDATE job_runs
		SET
			state = 'pending',
			available_at = now(),
			locked_by = NULL,
			locked_at = NULL,
			finished_at = NULL,
			error_message = NULL,
			updated_at = now()
		WHERE id = $1
			AND state IN ('failed', 'cancelled')
		RETURNING `+jobRunColumns+`
	`, id))
}
