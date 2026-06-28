package storage

import (
	"context"
	"fmt"
	"time"
)

type UpstreamEventActivityStatsParams struct {
	ListUpstreamEventsParams
	Series []string
}

func (s *UpstreamEventStore) CountUpstreamEvents(ctx context.Context, params ListUpstreamEventsParams) (int, error) {
	filters := upstreamEventListFilterArgsFromParams(params)

	row := s.runner.QueryRow(ctx, `
		SELECT COUNT(*)::int
		FROM upstream_events
		WHERE `+upstreamEventListWhereClause+`
	`, filters.queryArgs()...)

	var total int
	if err := row.Scan(&total); err != nil {
		return 0, fmt.Errorf("count upstream events: %w", err)
	}

	return total, nil
}

func (s *UpstreamEventStore) UpstreamEventActivityStats(ctx context.Context, params UpstreamEventActivityStatsParams) (ActivityStats, error) {
	if params.ReceivedAfter == nil || params.ReceivedBefore == nil {
		return ActivityStats{}, fmt.Errorf("upstream event activity stats: received_after and received_before are required")
	}

	from := params.ReceivedAfter.UTC()
	to := params.ReceivedBefore.UTC()
	if !to.After(from) {
		return ActivityStats{}, fmt.Errorf("upstream event activity stats: received_before must be after received_after")
	}

	series := append([]string(nil), params.Series...)
	if len(series) == 0 {
		series = []string{"created", "removed", "metadata_changed", "other"}
	}

	bucket := ChooseActivityStatsBucket(from, to)
	filters := upstreamEventListFilterArgsFromParams(params.ListUpstreamEventsParams)

	bucketUnit := string(bucket)
	rows, err := s.runner.Query(ctx, `
		SELECT date_trunc('`+bucketUnit+`', received_at) AS bucket_start, `+upstreamEventCategoryCase+` AS category, COUNT(*)::int
		FROM upstream_events
		WHERE `+upstreamEventListWhereClause+`
		GROUP BY 1, 2
		ORDER BY 1, 2
	`, filters.queryArgs()...)
	if err != nil {
		return ActivityStats{}, fmt.Errorf("upstream event activity stats: %w", err)
	}
	defer rows.Close()

	raw := map[time.Time]map[string]int{}
	for rows.Next() {
		var (
			bucketStart time.Time
			category    string
			count       int
		)
		if err := rows.Scan(&bucketStart, &category, &count); err != nil {
			return ActivityStats{}, fmt.Errorf("upstream event activity stats: %w", err)
		}
		start := truncateActivityBucket(bucketStart, bucket)
		if raw[start] == nil {
			raw[start] = map[string]int{}
		}
		raw[start][category] = count
	}
	if err := rows.Err(); err != nil {
		return ActivityStats{}, fmt.Errorf("upstream event activity stats: %w", err)
	}

	return BuildActivityStats(from, to, bucket, series, raw), nil
}
