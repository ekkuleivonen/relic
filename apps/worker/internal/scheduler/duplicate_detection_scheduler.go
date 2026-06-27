package scheduler

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/ekkuleivonen/relic/packages/storage"
)

const (
	detectDuplicatesTargetType        = "catalog"
	detectDuplicatesTargetID          = "catalog"
	defaultDuplicateDetectionInterval = 24 * time.Hour
)

type DuplicateDetectionScheduler struct {
	store             *storage.Store
	logger            *slog.Logger
	now               func() time.Time
	schedulerInterval time.Duration
	interval          time.Duration
}

type DuplicateDetectionSchedulerOptions struct {
	Store             *storage.Store
	Logger            *slog.Logger
	Now               func() time.Time
	SchedulerInterval time.Duration
	Interval          time.Duration
}

func NewDuplicateDetectionScheduler(options DuplicateDetectionSchedulerOptions) (*DuplicateDetectionScheduler, error) {
	if options.Store == nil {
		return nil, fmt.Errorf("create duplicate detection scheduler: storage store is required")
	}

	now := options.Now
	if now == nil {
		now = time.Now
	}
	logger := options.Logger
	if logger == nil {
		logger = slog.Default()
	}
	schedulerInterval := options.SchedulerInterval
	if schedulerInterval <= 0 {
		schedulerInterval = defaultSchedulerInterval
	}
	interval := options.Interval
	if interval <= 0 {
		interval = defaultDuplicateDetectionInterval
	}

	return &DuplicateDetectionScheduler{
		store:             options.Store,
		logger:            logger,
		now:               now,
		schedulerInterval: schedulerInterval,
		interval:          interval,
	}, nil
}

func (s *DuplicateDetectionScheduler) Run(ctx context.Context) error {
	if _, err := s.tick(ctx); err != nil {
		return err
	}

	ticker := time.NewTicker(s.schedulerInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
			if _, err := s.tick(ctx); err != nil {
				return err
			}
		}
	}
}

func (s *DuplicateDetectionScheduler) Tick(ctx context.Context) (bool, error) {
	return s.tick(ctx)
}

func (s *DuplicateDetectionScheduler) tick(ctx context.Context) (bool, error) {
	enqueued, err := s.enqueueIfDue(ctx)
	if err != nil {
		return enqueued, err
	}
	if enqueued {
		s.logger.Info("duplicate detection scheduled")
	}

	return enqueued, nil
}

func (s *DuplicateDetectionScheduler) enqueueIfDue(ctx context.Context) (bool, error) {
	active, err := s.store.JobRuns().HasActiveJobRunOfType(ctx, storage.JobTypeDetectDuplicates)
	if err != nil {
		return false, err
	}
	if active {
		return false, nil
	}

	lastFinished, err := s.store.JobRuns().LastSucceededJobRunFinishedAtOfType(ctx, storage.JobTypeDetectDuplicates)
	if err != nil {
		return false, err
	}

	if !DecideDuplicateDetection(lastFinished, s.now(), s.interval) {
		return false, nil
	}

	if _, err := s.store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:            storage.JobTypeDetectDuplicates,
		RequestedByType: "scheduler",
		TargetType:      detectDuplicatesTargetType,
		TargetID:        detectDuplicatesTargetID,
		Input:           storage.JobRunPayload{},
	}); err != nil {
		return false, err
	}

	return true, nil
}

func DecideDuplicateDetection(lastFinished *time.Time, now time.Time, interval time.Duration) bool {
	if lastFinished == nil {
		return true
	}

	return !now.Before(lastFinished.Add(interval))
}
