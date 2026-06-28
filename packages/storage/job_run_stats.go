package storage

import (
	"context"
	"fmt"
	"time"
)

type JobRunActivityStatsParams struct {
	ListJobRunsParams
	Series []string
}

func (s *JobRunStore) CountJobRuns(ctx context.Context, params ListJobRunsParams) (int, error) {
	filters := jobRunListFilterArgsFromParams(params)
	args := filters.queryArgs()

	row := s.runner.QueryRow(ctx, `
		SELECT COUNT(*)::int
		FROM job_runs
		WHERE `+jobRunListWhereClause+`
	`, args...)

	var total int
	if err := row.Scan(&total); err != nil {
		return 0, fmt.Errorf("count job runs: %w", err)
	}

	return total, nil
}

func (s *JobRunStore) JobRunActivityStats(ctx context.Context, params JobRunActivityStatsParams) (ActivityStats, error) {
	if params.CreatedAfter == nil || params.CreatedBefore == nil {
		return ActivityStats{}, fmt.Errorf("job run activity stats: created_after and created_before are required")
	}

	from := params.CreatedAfter.UTC()
	to := params.CreatedBefore.UTC()
	if !to.After(from) {
		return ActivityStats{}, fmt.Errorf("job run activity stats: created_before must be after created_after")
	}

	series := append([]string(nil), params.Series...)
	if len(series) == 0 {
		for _, jobType := range listJobRunTypeFilter(params.ListJobRunsParams) {
			series = append(series, jobType)
		}
	}

	bucket := ChooseActivityStatsBucket(from, to)
	filters := jobRunListFilterArgsFromParams(params.ListJobRunsParams)

	rows, err := s.runner.Query(ctx, fmt.Sprintf(`
		SELECT date_trunc('%s', created_at) AS bucket_start, type, COUNT(*)::int
		FROM job_runs
		WHERE `+jobRunListWhereClause+`
		GROUP BY 1, type
		ORDER BY 1, type
	`, bucket), filters.queryArgs()...)
	if err != nil {
		return ActivityStats{}, fmt.Errorf("job run activity stats: %w", err)
	}
	defer rows.Close()

	raw := map[time.Time]map[string]int{}
	for rows.Next() {
		var (
			bucketStart time.Time
			jobType     string
			count       int
		)
		if err := rows.Scan(&bucketStart, &jobType, &count); err != nil {
			return ActivityStats{}, fmt.Errorf("job run activity stats: %w", err)
		}
		start := truncateActivityBucket(bucketStart, bucket)
		if raw[start] == nil {
			raw[start] = map[string]int{}
		}
		raw[start][jobType] = count
	}
	if err := rows.Err(); err != nil {
		return ActivityStats{}, fmt.Errorf("job run activity stats: %w", err)
	}

	return BuildActivityStats(from, to, bucket, series, raw), nil
}
