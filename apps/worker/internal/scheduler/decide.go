package scheduler

import (
	"time"

	"github.com/ekkuleivonen/relic/packages/storage"
)

type ScanDecision string

const (
	ScanDecisionEnqueue     ScanDecision = "enqueue"
	ScanDecisionSkipDisabled ScanDecision = "skip_disabled"
	ScanDecisionSkipActive  ScanDecision = "skip_active"
	ScanDecisionSkipNotDue  ScanDecision = "skip_not_due"
)

func DecideScan(
	bucket storage.Bucket,
	lastFinished *time.Time,
	now time.Time,
	hasActive bool,
	defaultInterval time.Duration,
) ScanDecision {
	if !bucket.RelicConfig.ScanEnabled() {
		return ScanDecisionSkipDisabled
	}
	if hasActive {
		return ScanDecisionSkipActive
	}
	if !bucket.RelicConfig.ScanDue(lastFinished, now, defaultInterval) {
		return ScanDecisionSkipNotDue
	}

	return ScanDecisionEnqueue
}
