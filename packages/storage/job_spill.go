package storage

import (
	"context"
	"fmt"
)

type JobSpillRepository interface {
	InsertKeys(context.Context, string, []string) error
	FilterKeysNotInSpill(context.Context, string, []string) ([]string, error)
	DeleteForJobRun(context.Context, string) error
	CountKeys(context.Context, string) (int64, error)
	StreamObjectsInScopeMissingFromSpill(context.Context, string, ObjectScopeParams, func(Object) error) error
}

type JobSpillStore struct {
	runner Runner
}

func NewJobSpillStore(runner Runner) *JobSpillStore {
	return &JobSpillStore{runner: runner}
}

func (s *JobSpillStore) InsertKeys(ctx context.Context, jobRunID string, keys []string) error {
	if jobRunID == "" {
		return fmt.Errorf("insert job spill keys: job run id is required")
	}
	if len(keys) == 0 {
		return nil
	}

	_, err := s.runner.Exec(ctx, `
		INSERT INTO job_spill (job_run_id, spill_key)
		SELECT $1, key
		FROM unnest($2::text[]) AS key
		ON CONFLICT (job_run_id, spill_key) DO NOTHING
	`, jobRunID, keys)
	if err != nil {
		return fmt.Errorf("insert job spill keys: %w", err)
	}

	return nil
}

func (s *JobSpillStore) FilterKeysNotInSpill(ctx context.Context, jobRunID string, keys []string) ([]string, error) {
	if jobRunID == "" {
		return nil, fmt.Errorf("filter job spill keys: job run id is required")
	}
	if len(keys) == 0 {
		return nil, nil
	}

	rows, err := s.runner.Query(ctx, `
		SELECT key
		FROM unnest($2::text[]) AS key
		WHERE NOT EXISTS (
			SELECT 1
			FROM job_spill
			WHERE job_run_id = $1
				AND spill_key = key
		)
	`, jobRunID, keys)
	if err != nil {
		return nil, fmt.Errorf("filter job spill keys: %w", err)
	}
	defer rows.Close()

	pending := make([]string, 0, len(keys))
	for rows.Next() {
		var key string
		if err := rows.Scan(&key); err != nil {
			return nil, fmt.Errorf("filter job spill keys: %w", err)
		}
		pending = append(pending, key)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("filter job spill keys: %w", err)
	}

	return pending, nil
}

func (s *JobSpillStore) DeleteForJobRun(ctx context.Context, jobRunID string) error {
	if jobRunID == "" {
		return fmt.Errorf("delete job spill keys: job run id is required")
	}

	_, err := s.runner.Exec(ctx, `DELETE FROM job_spill WHERE job_run_id = $1`, jobRunID)
	if err != nil {
		return fmt.Errorf("delete job spill keys: %w", err)
	}

	return nil
}

func (s *JobSpillStore) CountKeys(ctx context.Context, jobRunID string) (int64, error) {
	if jobRunID == "" {
		return 0, fmt.Errorf("count job spill keys: job run id is required")
	}

	row := s.runner.QueryRow(ctx, `
		SELECT count(*)
		FROM job_spill
		WHERE job_run_id = $1
	`, jobRunID)

	var count int64
	if err := row.Scan(&count); err != nil {
		return 0, fmt.Errorf("count job spill keys: %w", err)
	}

	return count, nil
}

func (s *JobSpillStore) StreamObjectsInScopeMissingFromSpill(
	ctx context.Context,
	jobRunID string,
	scope ObjectScopeParams,
	fn func(Object) error,
) error {
	if jobRunID == "" {
		return fmt.Errorf("stream objects missing from spill: job run id is required")
	}
	if fn == nil {
		return fmt.Errorf("stream objects missing from spill: callback is required")
	}

	rows, err := s.runner.Query(ctx, `
		SELECT
			o.id,
			o.bucket_id,
			o.key,
			o.attributes,
			o.attribute_provenance,
			o.created_at,
			o.updated_at
		FROM objects AS o
		WHERE ($1 = '' OR o.bucket_id = $1)
			AND ($2 = '' OR starts_with(o.key, $2))
			AND NOT EXISTS (
				SELECT 1
				FROM job_spill AS spill
				WHERE spill.job_run_id = $3
					AND spill.spill_key = o.key
			)
		ORDER BY o.bucket_id ASC, o.key ASC
	`, scope.BucketID, scope.Prefix, jobRunID)
	if err != nil {
		return fmt.Errorf("stream objects missing from spill: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		object, err := scanObject(rows)
		if err != nil {
			return err
		}
		if err := fn(object); err != nil {
			return err
		}
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("stream objects missing from spill: %w", err)
	}

	return nil
}

var _ JobSpillRepository = (*JobSpillStore)(nil)
