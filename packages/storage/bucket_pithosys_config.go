package storage

import "time"

const DefaultScanInterval = 24 * time.Hour

const defaultScanIntervalString = "24h"

type BucketPithosysConfig struct {
	Scan BucketScanConfig `json:"scan"`
}

type BucketScanConfig struct {
	Enabled  *bool  `json:"enabled,omitempty"`
	Interval string `json:"interval,omitempty"`
}

func DefaultBucketPithosysConfig() BucketPithosysConfig {
	return BucketPithosysConfig{
		Scan: BucketScanConfig{
			Enabled:  BoolPtr(true),
			Interval: defaultScanIntervalString,
		},
	}
}

func BoolPtr(value bool) *bool {
	return &value
}

func (c BucketPithosysConfig) ScanEnabled() bool {
	if c.Scan.Enabled == nil {
		return true
	}

	return *c.Scan.Enabled
}

func (c BucketPithosysConfig) ScanInterval(fallback time.Duration) time.Duration {
	if c.Scan.Interval == "" {
		return fallback
	}

	parsed, err := time.ParseDuration(c.Scan.Interval)
	if err != nil || parsed <= 0 {
		return fallback
	}

	return parsed
}

func (c BucketPithosysConfig) ScanDue(lastFinished *time.Time, now time.Time, fallbackInterval time.Duration) bool {
	if !c.ScanEnabled() {
		return false
	}
	if lastFinished == nil {
		return true
	}

	return !now.Before(lastFinished.Add(c.ScanInterval(fallbackInterval)))
}
