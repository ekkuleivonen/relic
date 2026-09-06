package observability

import (
	"time"

	"github.com/elei-io/pithosys/packages/storage"
)

type ActivityStatsResponse struct {
	Bucket string                       `json:"bucket" example:"hour"`
	From   time.Time                    `json:"from"`
	To     time.Time                    `json:"to"`
	Series []string                     `json:"series"`
	Points []ActivityStatsPointResponse `json:"points"`
}

type ActivityStatsPointResponse struct {
	Start  time.Time      `json:"start"`
	Counts map[string]int `json:"counts"`
}

func ActivityStatsResponseFromStorage(stats storage.ActivityStats) ActivityStatsResponse {
	points := make([]ActivityStatsPointResponse, 0, len(stats.Points))
	for _, point := range stats.Points {
		counts := make(map[string]int, len(point.Counts))
		for key, value := range point.Counts {
			counts[key] = value
		}
		points = append(points, ActivityStatsPointResponse{
			Start:  point.Start,
			Counts: counts,
		})
	}

	return ActivityStatsResponse{
		Bucket: string(stats.Bucket),
		From:   stats.From,
		To:     stats.To,
		Series: append([]string(nil), stats.Series...),
		Points: points,
	}
}

func ParseOptionalTime(raw string) (*time.Time, error) {
	if raw == "" {
		return nil, nil
	}

	parsed, err := time.Parse(time.RFC3339, raw)
	if err != nil {
		return nil, err
	}

	value := parsed.UTC()
	return &value, nil
}
