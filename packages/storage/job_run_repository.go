package storage

import (
	"context"
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

type JobRunRepository interface {
	CreateJobRun(context.Context, CreateJobRunParams) (JobRun, error)
	GetJobRun(context.Context, string) (JobRun, error)
	ListJobRuns(context.Context, ListJobRunsParams) ([]JobRun, error)
	CountJobRuns(context.Context, ListJobRunsParams) (int, error)
	JobRunActivityStats(context.Context, JobRunActivityStatsParams) (ActivityStats, error)
	ClaimJobRun(context.Context, ClaimJobRunParams) (JobRun, error)
	UpdateJobRunProgress(context.Context, UpdateJobRunProgressParams) (JobRun, error)
	SucceedJobRun(context.Context, SucceedJobRunParams) (JobRun, error)
	RetryJobRun(context.Context, RetryJobRunParams) (JobRun, error)
	FailJobRun(context.Context, FailJobRunParams) (JobRun, error)
	HasActiveJobRun(context.Context, HasActiveJobRunParams) (bool, error)
	LastSucceededJobRunFinishedAt(context.Context, LastSucceededJobRunFinishedAtParams) (*time.Time, error)
	HasActiveJobRunOfType(context.Context, JobType) (bool, error)
	LastSucceededJobRunFinishedAtOfType(context.Context, JobType) (*time.Time, error)
}

type JobRunStore struct {
	runner Runner
}

func NewJobRunStore(runner Runner) *JobRunStore {
	return &JobRunStore{runner: runner}
}

type JobType string

const (
	JobTypeSyncBucket        JobType = "sync_bucket"
	JobTypeScanBucket        JobType = "scan_bucket"
	JobTypeImportObjects     JobType = "import_objects"
	JobTypeRemoveObjects     JobType = "remove_objects"
	JobTypeRefreshObjects    JobType = "refresh_objects"
	JobTypeExtractAttributes JobType = "extract_attributes"
	JobTypeDetectDuplicates  JobType = "detect_duplicates"
	JobTypeCleanupRuns       JobType = "cleanup_runs"
)

func IsKnownJobType(jobType JobType) bool {
	switch jobType {
	case JobTypeSyncBucket,
		JobTypeScanBucket,
		JobTypeImportObjects,
		JobTypeRemoveObjects,
		JobTypeRefreshObjects,
		JobTypeExtractAttributes,
		JobTypeDetectDuplicates,
		JobTypeCleanupRuns:
		return true
	default:
		return false
	}
}

type JobRunState string

const (
	JobRunStatePending   JobRunState = "pending"
	JobRunStateRunning   JobRunState = "running"
	JobRunStateSucceeded JobRunState = "succeeded"
	JobRunStateFailed    JobRunState = "failed"
	JobRunStateCancelled JobRunState = "cancelled"
)

type JobRunPayload map[string]any

type JobRun struct {
	ID              string
	Type            JobType
	State           JobRunState
	RequestedByType string
	RequestedByID   string
	TargetType      string
	TargetID        string
	Input           JobRunPayload
	Result          JobRunPayload
	Progress        JobRunPayload
	Attempt         int
	MaxAttempts     int
	AvailableAt     time.Time
	LockedBy        string
	LockedAt        *time.Time
	StartedAt       *time.Time
	FinishedAt      *time.Time
	ErrorMessage    string
	CreatedAt       time.Time
	UpdatedAt       time.Time
}

type CreateJobRunParams struct {
	Type            JobType
	RequestedByType string
	RequestedByID   string
	TargetType      string
	TargetID        string
	Input           JobRunPayload
	MaxAttempts     int
	AvailableAt     *time.Time
}

type ListJobRunsParams struct {
	Type            JobType
	Types           []JobType
	State           JobRunState
	RequestedByType string
	RequestedByID   string
	TargetType      string
	TargetID        string
	CreatedAfter    *time.Time
	CreatedBefore   *time.Time
	Limit           int
	Offset          int
}

type ClaimJobRunParams struct {
	WorkerID string
	Types    []JobType
}

type UpdateJobRunProgressParams struct {
	ID       string
	Progress JobRunPayload
}

type SucceedJobRunParams struct {
	ID     string
	Result JobRunPayload
}

type RetryJobRunParams struct {
	ID           string
	ErrorMessage string
	AvailableAt  *time.Time
}

type FailJobRunParams struct {
	ID           string
	ErrorMessage string
}

type HasActiveJobRunParams struct {
	Type       JobType
	TargetType string
	TargetID   string
}

type LastSucceededJobRunFinishedAtParams struct {
	Type       JobType
	TargetType string
	TargetID   string
}

func (s *JobRunStore) HasActiveJobRun(ctx context.Context, params HasActiveJobRunParams) (bool, error) {
	row := s.runner.QueryRow(ctx, `
		SELECT EXISTS (
			SELECT 1
			FROM job_runs
			WHERE type = $1
				AND target_type IS NOT DISTINCT FROM NULLIF($2, '')
				AND target_id IS NOT DISTINCT FROM NULLIF($3, '')
				AND state IN ('pending', 'running')
		)
	`, string(params.Type), params.TargetType, params.TargetID)

	var active bool
	if err := row.Scan(&active); err != nil {
		return false, fmt.Errorf("has active job run: %w", err)
	}

	return active, nil
}

func (s *JobRunStore) HasActiveJobRunOfType(ctx context.Context, jobType JobType) (bool, error) {
	row := s.runner.QueryRow(ctx, `
		SELECT EXISTS (
			SELECT 1
			FROM job_runs
			WHERE type = $1
				AND state IN ('pending', 'running')
		)
	`, string(jobType))

	var active bool
	if err := row.Scan(&active); err != nil {
		return false, fmt.Errorf("has active job run of type: %w", err)
	}

	return active, nil
}

func (s *JobRunStore) LastSucceededJobRunFinishedAt(ctx context.Context, params LastSucceededJobRunFinishedAtParams) (*time.Time, error) {
	row := s.runner.QueryRow(ctx, `
		SELECT finished_at
		FROM job_runs
		WHERE type = $1
			AND target_type IS NOT DISTINCT FROM NULLIF($2, '')
			AND target_id IS NOT DISTINCT FROM NULLIF($3, '')
			AND state = 'succeeded'
			AND finished_at IS NOT NULL
		ORDER BY finished_at DESC, id DESC
		LIMIT 1
	`, string(params.Type), params.TargetType, params.TargetID)

	var finishedAt sql.NullTime
	if err := row.Scan(&finishedAt); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, nil
		}
		return nil, fmt.Errorf("last succeeded job run finished at: %w", err)
	}
	if !finishedAt.Valid {
		return nil, nil
	}

	return &finishedAt.Time, nil
}

func (s *JobRunStore) LastSucceededJobRunFinishedAtOfType(ctx context.Context, jobType JobType) (*time.Time, error) {
	row := s.runner.QueryRow(ctx, `
		SELECT finished_at
		FROM job_runs
		WHERE type = $1
			AND state = 'succeeded'
			AND finished_at IS NOT NULL
		ORDER BY finished_at DESC, id DESC
		LIMIT 1
	`, string(jobType))

	var finishedAt sql.NullTime
	if err := row.Scan(&finishedAt); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, nil
		}
		return nil, fmt.Errorf("last succeeded job run finished at of type: %w", err)
	}
	if !finishedAt.Valid {
		return nil, nil
	}

	return &finishedAt.Time, nil
}

func (s *JobRunStore) CreateJobRun(ctx context.Context, params CreateJobRunParams) (JobRun, error) {
	id, err := newJobRunID()
	if err != nil {
		return JobRun{}, err
	}

	input, err := encodeJobRunPayload(params.Input)
	if err != nil {
		return JobRun{}, err
	}
	maxAttempts := params.MaxAttempts
	if maxAttempts <= 0 {
		maxAttempts = 1
	}

	return scanJobRun(s.runner.QueryRow(ctx, `
		INSERT INTO job_runs (
			id,
			type,
			requested_by_type,
			requested_by_id,
			target_type,
			target_id,
			input,
			max_attempts,
			available_at
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, COALESCE($9, now()))
		RETURNING
			id,
			type,
			state,
			requested_by_type,
			requested_by_id,
			target_type,
			target_id,
			input,
			result,
			progress,
			attempt,
			max_attempts,
			available_at,
			locked_by,
			locked_at,
			started_at,
			finished_at,
			error_message,
			created_at,
			updated_at
	`, id,
		string(params.Type),
		nullableString(params.RequestedByType),
		nullableString(params.RequestedByID),
		nullableString(params.TargetType),
		nullableString(params.TargetID),
		input,
		maxAttempts,
		params.AvailableAt,
	))
}

func (s *JobRunStore) GetJobRun(ctx context.Context, id string) (JobRun, error) {
	return scanJobRun(s.runner.QueryRow(ctx, `
		SELECT
			id,
			type,
			state,
			requested_by_type,
			requested_by_id,
			target_type,
			target_id,
			input,
			result,
			progress,
			attempt,
			max_attempts,
			available_at,
			locked_by,
			locked_at,
			started_at,
			finished_at,
			error_message,
			created_at,
			updated_at
		FROM job_runs
		WHERE id = $1
	`, id))
}

func (s *JobRunStore) ListJobRuns(ctx context.Context, params ListJobRunsParams) ([]JobRun, error) {
	limit := params.Limit
	if limit <= 0 {
		limit = 100
	}
	if limit > 500 {
		limit = 500
	}
	offset := params.Offset
	if offset < 0 {
		offset = 0
	}

	filters := jobRunListFilterArgsFromParams(params)
	args := append(filters.queryArgs(), limit, offset)

	rows, err := s.runner.Query(ctx, `
		SELECT
			id,
			type,
			state,
			requested_by_type,
			requested_by_id,
			target_type,
			target_id,
			input,
			result,
			progress,
			attempt,
			max_attempts,
			available_at,
			locked_by,
			locked_at,
			started_at,
			finished_at,
			error_message,
			created_at,
			updated_at
		FROM job_runs
		WHERE `+jobRunListWhereClause+`
		ORDER BY created_at DESC, id DESC
		LIMIT $9 OFFSET $10
	`, args...)
	if err != nil {
		return nil, fmt.Errorf("list job runs: %w", err)
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
		return nil, fmt.Errorf("list job runs: %w", err)
	}

	return runs, nil
}

func (s *JobRunStore) ClaimJobRun(ctx context.Context, params ClaimJobRunParams) (JobRun, error) {
	types := make([]string, 0, len(params.Types))
	for _, jobType := range params.Types {
		if jobType != "" {
			types = append(types, string(jobType))
		}
	}

	return scanJobRun(s.runner.QueryRow(ctx, `
		UPDATE job_runs
		SET
			state = 'running',
			locked_by = $1,
			locked_at = now(),
			started_at = COALESCE(started_at, now()),
			updated_at = now()
		WHERE id = (
			SELECT id
			FROM job_runs
			WHERE state = 'pending'
				AND available_at <= now()
				AND (cardinality($2::text[]) = 0 OR type = ANY($2::text[]))
			ORDER BY created_at ASC, id ASC
			FOR UPDATE SKIP LOCKED
			LIMIT 1
		)
		RETURNING
			id,
			type,
			state,
			requested_by_type,
			requested_by_id,
			target_type,
			target_id,
			input,
			result,
			progress,
			attempt,
			max_attempts,
			available_at,
			locked_by,
			locked_at,
			started_at,
			finished_at,
			error_message,
			created_at,
			updated_at
	`, params.WorkerID, types))
}

func (s *JobRunStore) UpdateJobRunProgress(ctx context.Context, params UpdateJobRunProgressParams) (JobRun, error) {
	progress, err := encodeJobRunPayload(params.Progress)
	if err != nil {
		return JobRun{}, err
	}

	return scanJobRun(s.runner.QueryRow(ctx, `
		UPDATE job_runs
		SET
			progress = $2,
			updated_at = now()
		WHERE id = $1
		RETURNING
			id,
			type,
			state,
			requested_by_type,
			requested_by_id,
			target_type,
			target_id,
			input,
			result,
			progress,
			attempt,
			max_attempts,
			available_at,
			locked_by,
			locked_at,
			started_at,
			finished_at,
			error_message,
			created_at,
			updated_at
	`, params.ID, progress))
}

func (s *JobRunStore) SucceedJobRun(ctx context.Context, params SucceedJobRunParams) (JobRun, error) {
	result, err := encodeJobRunPayload(params.Result)
	if err != nil {
		return JobRun{}, err
	}

	return scanJobRun(s.runner.QueryRow(ctx, `
		UPDATE job_runs
		SET
			state = 'succeeded',
			result = $2,
			locked_by = NULL,
			locked_at = NULL,
			finished_at = now(),
			error_message = NULL,
			updated_at = now()
		WHERE id = $1
		RETURNING
			id,
			type,
			state,
			requested_by_type,
			requested_by_id,
			target_type,
			target_id,
			input,
			result,
			progress,
			attempt,
			max_attempts,
			available_at,
			locked_by,
			locked_at,
			started_at,
			finished_at,
			error_message,
			created_at,
			updated_at
	`, params.ID, result))
}

func (s *JobRunStore) RetryJobRun(ctx context.Context, params RetryJobRunParams) (JobRun, error) {
	return scanJobRun(s.runner.QueryRow(ctx, `
		UPDATE job_runs
		SET
			state = 'pending',
			attempt = attempt + 1,
			available_at = COALESCE($2, now()),
			locked_by = NULL,
			locked_at = NULL,
			error_message = $3,
			updated_at = now()
		WHERE id = $1
			AND attempt < max_attempts
		RETURNING
			id,
			type,
			state,
			requested_by_type,
			requested_by_id,
			target_type,
			target_id,
			input,
			result,
			progress,
			attempt,
			max_attempts,
			available_at,
			locked_by,
			locked_at,
			started_at,
			finished_at,
			error_message,
			created_at,
			updated_at
	`, params.ID, params.AvailableAt, params.ErrorMessage))
}

func (s *JobRunStore) FailJobRun(ctx context.Context, params FailJobRunParams) (JobRun, error) {
	return scanJobRun(s.runner.QueryRow(ctx, `
		UPDATE job_runs
		SET
			state = 'failed',
			locked_by = NULL,
			locked_at = NULL,
			finished_at = now(),
			error_message = $2,
			updated_at = now()
		WHERE id = $1
		RETURNING
			id,
			type,
			state,
			requested_by_type,
			requested_by_id,
			target_type,
			target_id,
			input,
			result,
			progress,
			attempt,
			max_attempts,
			available_at,
			locked_by,
			locked_at,
			started_at,
			finished_at,
			error_message,
			created_at,
			updated_at
	`, params.ID, params.ErrorMessage))
}

func scanJobRun(row pgx.Row) (JobRun, error) {
	var (
		run             JobRun
		jobType         string
		state           string
		requestedByType sql.NullString
		requestedByID   sql.NullString
		targetType      sql.NullString
		targetID        sql.NullString
		inputBytes      []byte
		resultBytes     []byte
		progressBytes   []byte
		lockedBy        sql.NullString
		lockedAt        sql.NullTime
		startedAt       sql.NullTime
		finishedAt      sql.NullTime
		errorMessage    sql.NullString
	)

	err := row.Scan(
		&run.ID,
		&jobType,
		&state,
		&requestedByType,
		&requestedByID,
		&targetType,
		&targetID,
		&inputBytes,
		&resultBytes,
		&progressBytes,
		&run.Attempt,
		&run.MaxAttempts,
		&run.AvailableAt,
		&lockedBy,
		&lockedAt,
		&startedAt,
		&finishedAt,
		&errorMessage,
		&run.CreatedAt,
		&run.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return JobRun{}, ErrNotFound
	}
	if err != nil {
		return JobRun{}, fmt.Errorf("scan job run: %w", err)
	}

	run.Type = JobType(jobType)
	run.State = JobRunState(state)
	run.RequestedByType = requestedByType.String
	run.RequestedByID = requestedByID.String
	run.TargetType = targetType.String
	run.TargetID = targetID.String
	run.LockedBy = lockedBy.String
	run.LockedAt = nullableTimePtr(lockedAt)
	run.StartedAt = nullableTimePtr(startedAt)
	run.FinishedAt = nullableTimePtr(finishedAt)
	run.ErrorMessage = errorMessage.String

	if err := decodeJobRunPayload(inputBytes, &run.Input); err != nil {
		return JobRun{}, fmt.Errorf("decode job run input: %w", err)
	}
	if err := decodeJobRunPayload(resultBytes, &run.Result); err != nil {
		return JobRun{}, fmt.Errorf("decode job run result: %w", err)
	}
	if err := decodeJobRunPayload(progressBytes, &run.Progress); err != nil {
		return JobRun{}, fmt.Errorf("decode job run progress: %w", err)
	}

	return run, nil
}

func encodeJobRunPayload(payload JobRunPayload) ([]byte, error) {
	if payload == nil {
		payload = JobRunPayload{}
	}

	encoded, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("encode job run payload: %w", err)
	}

	return encoded, nil
}

func decodeJobRunPayload(data []byte, target *JobRunPayload) error {
	if len(data) == 0 {
		*target = JobRunPayload{}
		return nil
	}
	if err := json.Unmarshal(data, target); err != nil {
		return err
	}
	if *target == nil {
		*target = JobRunPayload{}
	}

	return nil
}

func listJobRunTypeFilter(params ListJobRunsParams) []string {
	if len(params.Types) > 0 {
		types := make([]string, 0, len(params.Types))
		for _, jobType := range params.Types {
			if jobType != "" {
				types = append(types, string(jobType))
			}
		}

		return types
	}

	if params.Type != "" {
		return []string{string(params.Type)}
	}

	return []string{}
}

func nullableString(value string) *string {
	if value == "" {
		return nil
	}

	return &value
}

func nullableTimePtr(value sql.NullTime) *time.Time {
	if !value.Valid {
		return nil
	}

	return &value.Time
}

func newJobRunID() (string, error) {
	random := make([]byte, 16)
	if _, err := rand.Read(random); err != nil {
		return "", fmt.Errorf("generate job run id: %w", err)
	}

	return "jobrun_" + hex.EncodeToString(random), nil
}
