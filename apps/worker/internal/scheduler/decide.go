package scheduler

import (
	"time"
)

type ScanDecision string

const (
	ScanDecisionEnqueue      ScanDecision = "enqueue"
	ScanDecisionSkipActive   ScanDecision = "skip_active"
	ScanDecisionSkipNotDue   ScanDecision = "skip_not_due"
)

func DecideScan(
	lastFinished *time.Time,
	now time.Time,
	hasActive bool,
	interval time.Duration,
) ScanDecision {
	if hasActive {
		return ScanDecisionSkipActive
	}
	if lastFinished != nil && now.Before(lastFinished.Add(interval)) {
		return ScanDecisionSkipNotDue
	}

	return ScanDecisionEnqueue
}
