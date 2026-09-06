package storage

import (
	"context"
	"fmt"
)

type AwaitJobRunChildrenParams struct {
	ID       string
	Result   JobRunPayload
	Progress JobRunPayload
}

func PayloadBool(payload JobRunPayload, key string) bool {
	if payload == nil {
		return false
	}
	value, ok := payload[key]
	if !ok {
		return false
	}
	switch typed := value.(type) {
	case bool:
		return typed
	default:
		return false
	}
}

func (s *JobRunStore) AwaitJobRunChildren(ctx context.Context, params AwaitJobRunChildrenParams) (JobRun, error) {
	result, err := encodeJobRunPayload(params.Result)
	if err != nil {
		return JobRun{}, err
	}
	progress, err := encodeJobRunPayload(params.Progress)
	if err != nil {
		return JobRun{}, err
	}

	return scanJobRun(s.runner.QueryRow(ctx, `
		UPDATE job_runs
		SET
			result = $2,
			progress = CASE
				WHEN $3::jsonb = '{}'::jsonb THEN progress
				ELSE progress || $3::jsonb
			END,
			locked_by = NULL,
			locked_at = NULL,
			updated_at = now()
		WHERE id = $1
			AND state = 'running'
		RETURNING `+jobRunColumns+`
	`, params.ID, result, progress))
}

func (s *JobRunStore) ListAwaitingTraceRoots(ctx context.Context, limit int) ([]JobRun, error) {
	return s.listAwaitingTraceJobs(ctx, limit, true)
}

func (s *JobRunStore) ListAwaitingTraceJobs(ctx context.Context, limit int) ([]JobRun, error) {
	return s.listAwaitingTraceJobs(ctx, limit, false)
}

func (s *JobRunStore) listAwaitingTraceJobs(ctx context.Context, limit int, rootsOnly bool) ([]JobRun, error) {
	if limit <= 0 {
		limit = 100
	}
	if limit > 500 {
		limit = 500
	}

	query := `
		SELECT ` + jobRunColumns + `
		FROM job_runs
		WHERE state = 'running'
			AND COALESCE(result->>'await_children', 'false') = 'true'
	`
	if rootsOnly {
		query += `
			AND id = trace_id
		`
	}
	query += `
		ORDER BY created_at DESC, id DESC
		LIMIT $1
	`

	rows, err := s.runner.Query(ctx, query, limit)
	if err != nil {
		return nil, fmt.Errorf("list awaiting trace jobs: %w", err)
	}
	defer rows.Close()

	runs := []JobRun{}
	for rows.Next() {
		run, err := scanJobRun(rows)
		if err != nil {
			return nil, err
		}
		runs = append(runs, run)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("list awaiting trace jobs: %w", err)
	}

	return runs, nil
}

func TraceChildrenComplete(runs []JobRun) bool {
	for _, run := range runs {
		if IsRootJob(run) {
			continue
		}
		if run.State == JobRunStatePending || run.State == JobRunStateRunning {
			return false
		}
	}

	return true
}

func (s *JobRunStore) DirectChildrenComplete(ctx context.Context, parentID string) (bool, error) {
	if parentID == "" {
		return false, fmt.Errorf("direct children complete: parent id is required")
	}

	row := s.runner.QueryRow(ctx, `
		SELECT NOT EXISTS (
			SELECT 1
			FROM job_runs
			WHERE requested_by_type = 'job'
				AND requested_by_id = $1
				AND state IN ('pending', 'running')
		)
	`, parentID)

	var complete bool
	if err := row.Scan(&complete); err != nil {
		return false, fmt.Errorf("direct children complete: %w", err)
	}

	return complete, nil
}

func (s *JobRunStore) DirectChildrenFailed(ctx context.Context, parentID string) (bool, error) {
	if parentID == "" {
		return false, fmt.Errorf("direct children failed: parent id is required")
	}

	row := s.runner.QueryRow(ctx, `
		SELECT EXISTS (
			SELECT 1
			FROM job_runs
			WHERE requested_by_type = 'job'
				AND requested_by_id = $1
				AND state = 'failed'
		)
	`, parentID)

	var failed bool
	if err := row.Scan(&failed); err != nil {
		return false, fmt.Errorf("direct children failed: %w", err)
	}

	return failed, nil
}

func TraceProgressRollup(summary TraceSummary) JobRunPayload {
	phase := summary.Phase
	switch {
	case summary.Batches.Import.Active > 0 || summary.Batches.Import.Pending > 0:
		phase = "importing"
	case summary.Batches.Refresh.Active > 0 || summary.Batches.Refresh.Pending > 0:
		phase = "refreshing"
	case summary.Batches.Remove.Active > 0 || summary.Batches.Remove.Pending > 0:
		phase = "removing"
	case summary.ObjectsPlanned.Import > 0 && summary.Batches.Import.Done < summary.Batches.Import.Total:
		phase = "importing"
	case summary.ObjectsPlanned.Refresh > 0 && summary.Batches.Refresh.Done < summary.Batches.Refresh.Total:
		phase = "refreshing"
	case summary.ObjectsPlanned.Remove > 0 && summary.Batches.Remove.Done < summary.Batches.Remove.Total:
		phase = "removing"
	case phase == "" && summary.ObjectsListed > 0:
		phase = "listing"
	}

	return JobRunPayload{
		"phase":                 phase,
		"objects_listed":        summary.ObjectsListed,
		"import_objects_count":  summary.ObjectsPlanned.Import,
		"refresh_objects_count": summary.ObjectsPlanned.Refresh,
		"remove_objects_count":  summary.ObjectsPlanned.Remove,
		"objects_planned": map[string]any{
			"import":  summary.ObjectsPlanned.Import,
			"refresh": summary.ObjectsPlanned.Refresh,
			"remove":  summary.ObjectsPlanned.Remove,
		},
		"objects_applied": map[string]any{
			"imported":  summary.ObjectsApplied.Import,
			"refreshed": summary.ObjectsApplied.Refresh,
			"removed":   summary.ObjectsApplied.Remove,
		},
		"batches": map[string]any{
			"import":  batchStatePayload(summary.Batches.Import),
			"refresh": batchStatePayload(summary.Batches.Refresh),
			"remove":  batchStatePayload(summary.Batches.Remove),
		},
	}
}

func batchStatePayload(state TraceBatchState) map[string]any {
	return map[string]any{
		"total":   state.Total,
		"done":    state.Done,
		"failed":  state.Failed,
		"active":  state.Active,
		"pending": state.Pending,
	}
}

func (s *JobRunStore) FinalizeAwaitingJob(ctx context.Context, job JobRun, summary TraceSummary) (bool, error) {
	if job.State != JobRunStateRunning || !PayloadBool(job.Result, "await_children") {
		return false, nil
	}

	complete, err := s.DirectChildrenComplete(ctx, job.ID)
	if err != nil {
		return false, err
	}
	if !complete {
		return false, nil
	}

	failed, err := s.DirectChildrenFailed(ctx, job.ID)
	if err != nil {
		return false, err
	}
	if failed {
		if _, err := s.FailJobRun(ctx, FailJobRunParams{
			ID:           job.ID,
			ErrorMessage: traceFailureMessage(summary),
		}); err != nil {
			return false, err
		}
		return true, nil
	}

	result := cloneJobRunPayload(job.Result)
	if IsRootJob(job) {
		for key, value := range TraceProgressRollup(summary) {
			result[key] = value
		}
		result["phase"] = terminalTracePhase(summary)
	}

	if _, err := s.SucceedJobRun(ctx, SucceedJobRunParams{
		ID:     job.ID,
		Result: result,
	}); err != nil {
		return false, err
	}

	return true, nil
}

func (s *JobRunStore) FinalizeAwaitingTrace(ctx context.Context, traceID string, summary TraceSummary) (int, error) {
	if traceID == "" {
		return 0, fmt.Errorf("finalize awaiting trace: trace id is required")
	}

	awaiting, err := s.listAwaitingTraceJobsForTrace(ctx, traceID)
	if err != nil {
		return 0, err
	}

	finalized := 0
	for _, run := range awaiting {
		done, err := s.FinalizeAwaitingJob(ctx, run, summary)
		if err != nil {
			return finalized, err
		}
		if done {
			finalized++
		}
	}

	return finalized, nil
}

func (s *JobRunStore) listAwaitingTraceJobsForTrace(ctx context.Context, traceID string) ([]JobRun, error) {
	rows, err := s.runner.Query(ctx, `
		SELECT `+jobRunColumns+`
		FROM job_runs
		WHERE trace_id = $1
			AND state = 'running'
			AND COALESCE(result->>'await_children', 'false') = 'true'
		ORDER BY created_at ASC, id ASC
	`, traceID)
	if err != nil {
		return nil, fmt.Errorf("list awaiting trace jobs for trace: %w", err)
	}
	defer rows.Close()

	runs := []JobRun{}
	for rows.Next() {
		run, err := scanJobRun(rows)
		if err != nil {
			return nil, err
		}
		runs = append(runs, run)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("list awaiting trace jobs for trace: %w", err)
	}

	return runs, nil
}

func terminalTracePhase(summary TraceSummary) string {
	switch {
	case summary.ObjectsPlanned.Remove > 0:
		return "removed"
	case summary.ObjectsPlanned.Refresh > 0:
		return "refreshed"
	case summary.ObjectsPlanned.Import > 0:
		return "imported"
	default:
		return "completed"
	}
}

func traceFailureMessage(summary TraceSummary) string {
	failed := summary.Batches.Import.Failed + summary.Batches.Refresh.Failed + summary.Batches.Remove.Failed
	if failed == 0 {
		return "trace failed"
	}

	return fmt.Sprintf("trace failed: %d child job batch(es) failed", failed)
}

func cloneJobRunPayload(payload JobRunPayload) JobRunPayload {
	if payload == nil {
		return JobRunPayload{}
	}

	cloned := JobRunPayload{}
	for key, value := range payload {
		cloned[key] = value
	}

	return cloned
}
