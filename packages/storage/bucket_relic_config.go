package storage

import "time"

const DefaultScanInterval = 24 * time.Hour

const defaultScanIntervalString = "24h"

type BucketRelicConfig struct {
	Scan BucketScanConfig `json:"scan"`
}

type BucketScanConfig struct {
	Enabled  *bool  `json:"enabled,omitempty"`
	Interval string `json:"interval,omitempty"`
}

func DefaultBucketRelicConfig() BucketRelicConfig {
	return BucketRelicConfig{
		Scan: BucketScanConfig{
			Enabled:  BoolPtr(true),
			Interval: defaultScanIntervalString,
		},
	}
}

func BoolPtr(value bool) *bool {
	return &value
}

func (c BucketRelicConfig) ScanEnabled() bool {
	if c.Scan.Enabled == nil {
		return true
	}

	return *c.Scan.Enabled
}

func (c BucketRelicConfig) ScanInterval(fallback time.Duration) time.Duration {
	if c.Scan.Interval == "" {
		return fallback
	}

	parsed, err := time.ParseDuration(c.Scan.Interval)
	if err != nil || parsed <= 0 {
		return fallback
	}

	return parsed
}

func (c BucketRelicConfig) ScanDue(lastFinished *time.Time, now time.Time, fallbackInterval time.Duration) bool {
	if !c.ScanEnabled() {
		return false
	}
	if lastFinished == nil {
		return true
	}

	return !now.Before(lastFinished.Add(c.ScanInterval(fallbackInterval)))
}
