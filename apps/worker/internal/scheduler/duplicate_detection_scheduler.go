package scheduler

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/elei-io/pithosys/apps/worker/internal/settings"
	"github.com/elei-io/pithosys/packages/storage"
)

const (
	detectDuplicatesTargetType = "catalog"
	detectDuplicatesTargetID   = "catalog"
)

type DuplicateDetectionScheduler struct {
	store    *storage.Store
	logger   *slog.Logger
	now      func() time.Time
	settings settings.Reader
}

type DuplicateDetectionSchedulerOptions struct {
	Store    *storage.Store
	Logger   *slog.Logger
	Now      func() time.Time
	Settings settings.Reader
}

func NewDuplicateDetectionScheduler(options DuplicateDetectionSchedulerOptions) (*DuplicateDetectionScheduler, error) {
	if options.Store == nil {
		return nil, fmt.Errorf("create duplicate detection scheduler: storage store is required")
	}
	if options.Settings == nil {
		return nil, fmt.Errorf("create duplicate detection scheduler: settings reader is required")
	}

	now := options.Now
	if now == nil {
		now = time.Now
	}
	logger := options.Logger
	if logger == nil {
		logger = slog.Default()
	}

	return &DuplicateDetectionScheduler{
		store:    options.Store,
		logger:   logger,
		now:      now,
		settings: options.Settings,
	}, nil
}

func (s *DuplicateDetectionScheduler) Run(ctx context.Context) error {
	for {
		if _, err := s.tick(ctx); err != nil {
			return err
		}

		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(s.settings.Duration(storage.SettingWorkerDuplicateDetectionSchedulerInterval)):
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

	interval := s.settings.Duration(storage.SettingDuplicateDetectionInterval)
	if !DecideDuplicateDetection(lastFinished, s.now(), interval) {
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
