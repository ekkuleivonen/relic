package scheduler

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/elei-io/pithosys/apps/worker/internal/settings"
	"github.com/elei-io/pithosys/packages/storage"
)

type ScanScheduler struct {
	store    *storage.Store
	logger   *slog.Logger
	now      func() time.Time
	settings settings.Reader
}

type ScanSchedulerOptions struct {
	Store    *storage.Store
	Logger   *slog.Logger
	Now      func() time.Time
	Settings settings.Reader
}

func NewScanScheduler(options ScanSchedulerOptions) (*ScanScheduler, error) {
	if options.Store == nil {
		return nil, fmt.Errorf("create scan scheduler: storage store is required")
	}
	if options.Settings == nil {
		return nil, fmt.Errorf("create scan scheduler: settings reader is required")
	}

	now := options.Now
	if now == nil {
		now = time.Now
	}
	logger := options.Logger
	if logger == nil {
		logger = slog.Default()
	}

	return &ScanScheduler{
		store:    options.Store,
		logger:   logger,
		now:      now,
		settings: options.Settings,
	}, nil
}

func (s *ScanScheduler) Run(ctx context.Context) error {
	for {
		if _, err := s.tick(ctx); err != nil {
			return err
		}

		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(s.settings.Duration(storage.SettingWorkerScanSchedulerInterval)):
		}
	}
}

func (s *ScanScheduler) Tick(ctx context.Context) (int, error) {
	return s.tick(ctx)
}

func (s *ScanScheduler) tick(ctx context.Context) (int, error) {
	enqueued, err := s.enqueueDueScans(ctx)
	if err != nil {
		return enqueued, err
	}
	if enqueued > 0 {
		s.logger.Info("scan scheduler tick complete", "enqueued", enqueued)
	}

	return enqueued, nil
}

func (s *ScanScheduler) enqueueDueScans(ctx context.Context) (int, error) {
	buckets, err := s.store.Buckets().ListBuckets(ctx, storage.ListBucketsParams{Limit: 500})
	if err != nil {
		return 0, err
	}

	now := s.now()
	scanInterval := s.settings.Duration(storage.SettingScanBucketInterval)
	stagger := s.settings.Duration(storage.SettingWorkerScanStagger)
	enqueued := 0

	for _, bucket := range buckets {
		activeWork, err := s.store.JobRuns().HasActiveWorkForTarget(ctx, storage.HasActiveWorkForTargetParams{
			TargetType: "bucket",
			TargetID:   bucket.ID,
			StaleAfter: s.settings.Duration(storage.SettingWorkerJobStaleTimeout),
		})
		if err != nil {
			return enqueued, err
		}
		if activeWork {
			continue
		}

		lastFinished, err := s.store.JobRuns().LastJobRunFinishedAt(ctx, storage.LastJobRunFinishedAtParams{
			Type:       storage.JobTypeScanBucket,
			TargetType: "bucket",
			TargetID:   bucket.ID,
		})
		if err != nil {
			return enqueued, err
		}

		decision := DecideScan(lastFinished, now, activeWork, scanInterval)
		if decision != ScanDecisionEnqueue {
			continue
		}

		if _, err := s.store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
			Type:            storage.JobTypeScanBucket,
			RequestedByType: "scheduler",
			TargetType:      "bucket",
			TargetID:        bucket.ID,
			Input: storage.JobRunPayload{
				"bucket_id": bucket.ID,
			},
		}); err != nil {
			return enqueued, err
		}

		enqueued++
		s.logger.Info("scan scheduled", "bucket_id", bucket.ID)

		if stagger > 0 {
			select {
			case <-ctx.Done():
				return enqueued, ctx.Err()
			case <-time.After(stagger):
			}
		}
	}

	return enqueued, nil
}
