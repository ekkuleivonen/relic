package scan_bucket

import "time"

const (
	defaultMaxObjectsListed int64 = 100_000
	defaultMaxScanDuration        = 10 * time.Minute
)

type ScanBudgetConfig struct {
	MaxObjectsListed int64
	MaxDuration      time.Duration
}

type ScanBudget struct {
	maxObjects    int64
	deadline      time.Time
	objectsListed int64
	now           func() time.Time
}

func NewScanBudget(cfg ScanBudgetConfig, start time.Time, now func() time.Time) *ScanBudget {
	if now == nil {
		now = time.Now
	}

	maxObjects := cfg.MaxObjectsListed
	if maxObjects <= 0 {
		maxObjects = defaultMaxObjectsListed
	}
	maxDuration := cfg.MaxDuration
	if maxDuration <= 0 {
		maxDuration = defaultMaxScanDuration
	}

	return &ScanBudget{
		maxObjects: maxObjects,
		deadline:   start.Add(maxDuration),
		now:        now,
	}
}

func (b *ScanBudget) Allow(count int) bool {
	if b.now().After(b.deadline) {
		return false
	}
	if count <= 0 {
		return true
	}
	if b.objectsListed+int64(count) > b.maxObjects {
		return false
	}

	return true
}

func (b *ScanBudget) Record(count int) {
	if count > 0 {
		b.objectsListed += int64(count)
	}
}

func (b *ScanBudget) ObjectsListed() int64 {
	return b.objectsListed
}
