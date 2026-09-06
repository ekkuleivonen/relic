package storage

import (
	"context"
	"fmt"
	"time"
)

type TraceSummary struct {
	TraceID       string
	RootJobRunID  string
	State         JobRunState
	Phase         string
	ObjectsListed int64
	ObjectsPlanned TraceObjectCounts
	ObjectsApplied TraceObjectCounts
	Batches        TraceBatchCounts
	StaleSeconds   int64
	JobCounts      map[JobType]TraceJobTypeCounts
}

type TraceObjectCounts struct {
	Import  int64
	Refresh int64
	Remove  int64
}

type TraceBatchCounts struct {
	Import  TraceBatchState
	Refresh TraceBatchState
	Remove  TraceBatchState
}

type TraceBatchState struct {
	Total    int
	Done     int
	Failed   int
	Active   int
	Pending  int
}

type TraceJobTypeCounts struct {
	Total     int
	Pending   int
	Running   int
	Succeeded int
	Failed    int
	Cancelled int
}

type HasActiveWorkForTargetParams struct {
	TargetType string
	TargetID   string
	StaleAfter time.Duration
}

func IsRootJob(run JobRun) bool {
	return run.ID == run.TraceID
}

func (s *JobRunStore) IsTraceActive(ctx context.Context, traceID string) (bool, error) {
	if traceID == "" {
		return false, fmt.Errorf("is trace active: trace id is required")
	}

	row := s.runner.QueryRow(ctx, `
		SELECT EXISTS (
			SELECT 1
			FROM job_runs
			WHERE trace_id = $1
				AND state IN ('pending', 'running')
		)
	`, traceID)

	var active bool
	if err := row.Scan(&active); err != nil {
		return false, fmt.Errorf("is trace active: %w", err)
	}

	return active, nil
}

const activeCatalogTraceWorkForTargetPredicate = `
	target_type IS NOT DISTINCT FROM $1
	AND target_id IS NOT DISTINCT FROM $2
	AND state IN ('pending', 'running')
	AND NOT (
		state = 'running'
		AND locked_by IS NOT NULL
		AND updated_at < now() - $3::interval
	)
	AND EXISTS (
		SELECT 1
		FROM job_runs AS root
		WHERE root.id = job_runs.trace_id
			AND root.id = root.trace_id
			AND root.type IN ('sync_bucket', 'scan_bucket')
			AND root.target_type IS NOT DISTINCT FROM $1
			AND root.target_id IS NOT DISTINCT FROM $2
	)
`

func (s *JobRunStore) HasActiveWorkForTarget(ctx context.Context, params HasActiveWorkForTargetParams) (bool, error) {
	if params.TargetType == "" {
		return false, fmt.Errorf("has active work for target: target type is required")
	}
	if params.TargetID == "" {
		return false, fmt.Errorf("has active work for target: target id is required")
	}

	staleAfter := ResolveJobStaleTimeout(params.StaleAfter)

	row := s.runner.QueryRow(ctx, `
		SELECT EXISTS (
			SELECT 1
			FROM job_runs
			WHERE `+activeCatalogTraceWorkForTargetPredicate+`
		)
	`, params.TargetType, params.TargetID, staleAfter)

	var active bool
	if err := row.Scan(&active); err != nil {
		return false, fmt.Errorf("has active work for target: %w", err)
	}

	return active, nil
}

func (s *JobRunStore) FindActiveWorkForTarget(ctx context.Context, params HasActiveWorkForTargetParams) (JobRun, error) {
	if params.TargetType == "" {
		return JobRun{}, fmt.Errorf("find active work for target: target type is required")
	}
	if params.TargetID == "" {
		return JobRun{}, fmt.Errorf("find active work for target: target id is required")
	}

	staleAfter := ResolveJobStaleTimeout(params.StaleAfter)

	return scanJobRun(s.runner.QueryRow(ctx, `
		SELECT `+jobRunColumns+`
		FROM job_runs
		WHERE `+activeCatalogTraceWorkForTargetPredicate+`
		ORDER BY created_at DESC, id DESC
		LIMIT 1
	`, params.TargetType, params.TargetID, staleAfter))
}

const supersededByUserSyncErrorMessage = "cancelled: superseded by user-initiated sync"

func (s *JobRunStore) FailActiveScanJobsForTarget(ctx context.Context, params HasActiveWorkForTargetParams) (int, error) {
	if params.TargetType == "" {
		return 0, fmt.Errorf("fail active scan jobs for target: target type is required")
	}
	if params.TargetID == "" {
		return 0, fmt.Errorf("fail active scan jobs for target: target id is required")
	}

	rows, err := s.runner.Query(ctx, `
		UPDATE job_runs
		SET
			state = 'failed',
			locked_by = NULL,
			locked_at = NULL,
			finished_at = now(),
			error_message = $4,
			updated_at = now()
		WHERE target_type IS NOT DISTINCT FROM $1
			AND target_id IS NOT DISTINCT FROM $2
			AND type = $3
			AND state IN ('pending', 'running')
		RETURNING id
	`, params.TargetType, params.TargetID, JobTypeScanBucket, supersededByUserSyncErrorMessage)
	if err != nil {
		return 0, fmt.Errorf("fail active scan jobs for target: %w", err)
	}
	defer rows.Close()

	failed := 0
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return failed, fmt.Errorf("fail active scan jobs for target: %w", err)
		}
		failed++
	}
	if err := rows.Err(); err != nil {
		return failed, fmt.Errorf("fail active scan jobs for target: %w", err)
	}

	return failed, nil
}

func (s *JobRunStore) SummarizeTrace(ctx context.Context, traceID string) (TraceSummary, error) {
	if traceID == "" {
		return TraceSummary{}, fmt.Errorf("summarize trace: trace id is required")
	}

	root, err := s.GetJobRun(ctx, traceID)
	if err != nil {
		return TraceSummary{}, err
	}
	if !IsRootJob(root) {
		return TraceSummary{}, fmt.Errorf("summarize trace: root job run not found for trace %q", traceID)
	}

	summary := TraceSummary{
		TraceID:      traceID,
		RootJobRunID: traceID,
		JobCounts:    map[JobType]TraceJobTypeCounts{},
	}

	if err := s.loadTraceStateSummary(ctx, traceID, &summary); err != nil {
		return TraceSummary{}, err
	}
	if err := s.loadTraceBatchSummary(ctx, traceID, &summary); err != nil {
		return TraceSummary{}, err
	}
	if err := s.loadTraceAppliedSummary(ctx, traceID, &summary); err != nil {
		return TraceSummary{}, err
	}

	summary.Phase = PayloadString(root.Progress, "phase")
	summary.ObjectsListed = PayloadInt64(root.Progress, "objects_listed")
	if summary.ObjectsListed == 0 {
		summary.ObjectsListed = PayloadInt64(root.Result, "objects_seen")
	}
	summary.ObjectsPlanned = TraceObjectCounts{
		Import:  PayloadInt64(root.Progress, "import_objects_count"),
		Refresh: PayloadInt64(root.Progress, "refresh_objects_count"),
		Remove:  PayloadInt64(root.Progress, "remove_objects_count"),
	}
	if summary.ObjectsPlanned.Import == 0 {
		summary.ObjectsPlanned.Import = PayloadInt64(root.Result, "import_objects_count")
	}
	if summary.ObjectsPlanned.Refresh == 0 {
		summary.ObjectsPlanned.Refresh = PayloadInt64(root.Result, "refresh_objects_count")
	}
	if summary.ObjectsPlanned.Remove == 0 {
		summary.ObjectsPlanned.Remove = PayloadInt64(root.Result, "remove_objects_count")
	}
	summary.StaleSeconds = int64(time.Since(root.UpdatedAt).Seconds())

	return summary, nil
}

func (s *JobRunStore) loadTraceStateSummary(ctx context.Context, traceID string, summary *TraceSummary) error {
	row := s.runner.QueryRow(ctx, `
		SELECT
			COALESCE(bool_or(state IN ('pending', 'running')), false),
			COALESCE(bool_or(state = 'failed'), false),
			COALESCE(bool_or(state = 'cancelled'), false)
		FROM job_runs
		WHERE trace_id = $1
	`, traceID)

	var hasActive bool
	var hasFailed bool
	var hasCancelled bool
	if err := row.Scan(&hasActive, &hasFailed, &hasCancelled); err != nil {
		return fmt.Errorf("summarize trace state: %w", err)
	}

	switch {
	case hasActive:
		summary.State = JobRunStateRunning
	case hasFailed:
		summary.State = JobRunStateFailed
	case hasCancelled:
		summary.State = JobRunStateCancelled
	default:
		summary.State = JobRunStateSucceeded
	}

	rows, err := s.runner.Query(ctx, `
		SELECT type, state, count(*)
		FROM job_runs
		WHERE trace_id = $1
		GROUP BY type, state
	`, traceID)
	if err != nil {
		return fmt.Errorf("summarize trace job counts: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var jobType string
		var state string
		var count int
		if err := rows.Scan(&jobType, &state, &count); err != nil {
			return fmt.Errorf("summarize trace job counts: %w", err)
		}

		counts := summary.JobCounts[JobType(jobType)]
		counts.Total += count
		switch JobRunState(state) {
		case JobRunStatePending:
			counts.Pending += count
		case JobRunStateRunning:
			counts.Running += count
		case JobRunStateSucceeded:
			counts.Succeeded += count
		case JobRunStateFailed:
			counts.Failed += count
		case JobRunStateCancelled:
			counts.Cancelled += count
		}
		summary.JobCounts[JobType(jobType)] = counts
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("summarize trace job counts: %w", err)
	}

	return nil
}

func (s *JobRunStore) loadTraceBatchSummary(ctx context.Context, traceID string, summary *TraceSummary) error {
	rows, err := s.runner.Query(ctx, `
		SELECT type, state, count(*)
		FROM job_runs
		WHERE trace_id = $1
			AND type = ANY($2::text[])
		GROUP BY type, state
	`, traceID, []string{
		string(JobTypeImportObjects),
		string(JobTypeRefreshObjects),
		string(JobTypeRemoveObjects),
	})
	if err != nil {
		return fmt.Errorf("summarize trace batches: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var jobType string
		var state string
		var count int
		if err := rows.Scan(&jobType, &state, &count); err != nil {
			return fmt.Errorf("summarize trace batches: %w", err)
		}

		target := batchStateForType(summary, JobType(jobType))
		if target == nil {
			continue
		}
		target.Total += count
		switch JobRunState(state) {
		case JobRunStatePending:
			target.Pending += count
		case JobRunStateRunning:
			target.Active += count
		case JobRunStateSucceeded:
			target.Done += count
		case JobRunStateFailed:
			target.Failed += count
		}
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("summarize trace batches: %w", err)
	}

	return nil
}

func batchStateForType(summary *TraceSummary, jobType JobType) *TraceBatchState {
	switch jobType {
	case JobTypeImportObjects:
		return &summary.Batches.Import
	case JobTypeRefreshObjects:
		return &summary.Batches.Refresh
	case JobTypeRemoveObjects:
		return &summary.Batches.Remove
	default:
		return nil
	}
}

func (s *JobRunStore) loadTraceAppliedSummary(ctx context.Context, traceID string, summary *TraceSummary) error {
	row := s.runner.QueryRow(ctx, `
		SELECT
			COALESCE(SUM(
				CASE WHEN type = $2 THEN COALESCE(NULLIF(result->>'objects_imported', '')::bigint, 0) ELSE 0 END
			), 0),
			COALESCE(SUM(
				CASE WHEN type = $3 THEN COALESCE(NULLIF(result->>'objects_refreshed', '')::bigint, 0) ELSE 0 END
			), 0),
			COALESCE(SUM(
				CASE WHEN type = $4 THEN COALESCE(NULLIF(result->>'objects_deleted', '')::bigint, 0) ELSE 0 END
			), 0)
		FROM job_runs
		WHERE trace_id = $1
	`, traceID, JobTypeImportObjects, JobTypeRefreshObjects, JobTypeRemoveObjects)

	if err := row.Scan(&summary.ObjectsApplied.Import, &summary.ObjectsApplied.Refresh, &summary.ObjectsApplied.Remove); err != nil {
		return fmt.Errorf("summarize trace applied counts: %w", err)
	}

	return nil
}

func PayloadString(payload JobRunPayload, key string) string {
	return payloadString(payload, key)
}

func payloadString(payload JobRunPayload, key string) string {
	value, ok := payload[key]
	if !ok || value == nil {
		return ""
	}
	if typed, ok := value.(string); ok {
		return typed
	}

	return fmt.Sprint(value)
}

func PayloadInt64(payload JobRunPayload, key string) int64 {
	return payloadInt64(payload, key)
}

func payloadInt64(payload JobRunPayload, key string) int64 {
	value, ok := payload[key]
	if !ok || value == nil {
		return 0
	}

	switch typed := value.(type) {
	case int:
		return int64(typed)
	case int64:
		return typed
	case float64:
		return int64(typed)
	default:
		return 0
	}
}
