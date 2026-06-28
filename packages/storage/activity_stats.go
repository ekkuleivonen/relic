package storage

import "time"

type ActivityStatsBucket string

const (
	ActivityStatsBucketHour ActivityStatsBucket = "hour"
	ActivityStatsBucketDay  ActivityStatsBucket = "day"
)

type ActivityStatsPoint struct {
	Start  time.Time
	Counts map[string]int
}

type ActivityStats struct {
	Bucket ActivityStatsBucket
	From   time.Time
	To     time.Time
	Series []string
	Points []ActivityStatsPoint
}

func ChooseActivityStatsBucket(from, to time.Time) ActivityStatsBucket {
	if to.Sub(from) <= 48*time.Hour {
		return ActivityStatsBucketHour
	}

	return ActivityStatsBucketDay
}

func BuildActivityStats(from, to time.Time, bucket ActivityStatsBucket, series []string, raw map[time.Time]map[string]int) ActivityStats {
	points := make([]ActivityStatsPoint, 0)
	for start := truncateActivityBucket(from.UTC(), bucket); start.Before(to); start = advanceActivityBucket(start, bucket) {
		counts := make(map[string]int, len(series))
		for _, key := range series {
			if bucketCounts, ok := raw[start]; ok {
				counts[key] = bucketCounts[key]
			}
		}
		points = append(points, ActivityStatsPoint{
			Start:  start,
			Counts: counts,
		})
	}

	return ActivityStats{
		Bucket: bucket,
		From:   from,
		To:     to,
		Series: append([]string(nil), series...),
		Points: points,
	}
}

func truncateActivityBucket(value time.Time, bucket ActivityStatsBucket) time.Time {
	value = value.UTC()
	switch bucket {
	case ActivityStatsBucketHour:
		return time.Date(value.Year(), value.Month(), value.Day(), value.Hour(), 0, 0, 0, time.UTC)
	default:
		return time.Date(value.Year(), value.Month(), value.Day(), 0, 0, 0, 0, time.UTC)
	}
}

func advanceActivityBucket(value time.Time, bucket ActivityStatsBucket) time.Time {
	switch bucket {
	case ActivityStatsBucketHour:
		return value.Add(time.Hour)
	default:
		return value.AddDate(0, 0, 1)
	}
}
