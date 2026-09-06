package storage

import (
	"context"
	"fmt"
	"time"
)

const DefaultJobStaleTimeout = 15 * time.Minute

const staleLockedJobErrorMessage = "job timed out: worker stopped making progress"

type ReclaimStaleLockedJobsParams struct {
	StaleAfter time.Duration
	Limit      int
}

func ResolveJobStaleTimeout(staleAfter time.Duration) time.Duration {
	if staleAfter > 0 {
		return staleAfter
	}

	return DefaultJobStaleTimeout
}

func (s *JobRunStore) ReclaimStaleLockedJobs(ctx context.Context, params ReclaimStaleLockedJobsParams) (int, error) {
	staleAfter := ResolveJobStaleTimeout(params.StaleAfter)
	limit := params.Limit
	if limit <= 0 {
		limit = 100
	}

	rows, err := s.runner.Query(ctx, `
		UPDATE job_runs
		SET
			state = 'failed',
			locked_by = NULL,
			locked_at = NULL,
			finished_at = now(),
			error_message = $3,
			updated_at = now()
		WHERE id IN (
			SELECT id
			FROM job_runs
			WHERE state = 'running'
				AND locked_by IS NOT NULL
				AND updated_at < now() - $1::interval
			ORDER BY updated_at ASC, id ASC
			LIMIT $2
			FOR UPDATE SKIP LOCKED
		)
		RETURNING id
	`, staleAfter, limit, staleLockedJobErrorMessage)
	if err != nil {
		return 0, fmt.Errorf("reclaim stale locked jobs: %w", err)
	}
	defer rows.Close()

	reclaimed := 0
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return reclaimed, fmt.Errorf("reclaim stale locked jobs: %w", err)
		}
		reclaimed++
	}
	if err := rows.Err(); err != nil {
		return reclaimed, fmt.Errorf("reclaim stale locked jobs: %w", err)
	}

	return reclaimed, nil
}
