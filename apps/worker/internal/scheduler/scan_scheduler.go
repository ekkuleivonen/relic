package scheduler

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/ekkuleivonen/relic/packages/storage"
)

const (
	defaultSchedulerInterval = 15 * time.Second
	defaultScanStagger         = 30 * time.Second
)

type ScanScheduler struct {
	store            *storage.Store
	logger           *slog.Logger
	now              func() time.Time
	schedulerInterval time.Duration
	defaultInterval  time.Duration
	stagger          time.Duration
}

type ScanSchedulerOptions struct {
	Store             *storage.Store
	Logger            *slog.Logger
	Now               func() time.Time
	SchedulerInterval time.Duration
	DefaultInterval   time.Duration
	Stagger           time.Duration
}

func NewScanScheduler(options ScanSchedulerOptions) (*ScanScheduler, error) {
	if options.Store == nil {
		return nil, fmt.Errorf("create scan scheduler: storage store is required")
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
	defaultInterval := options.DefaultInterval
	if defaultInterval <= 0 {
		defaultInterval = storage.DefaultScanInterval
	}
	stagger := options.Stagger
	if stagger <= 0 {
		stagger = defaultScanStagger
	}

	return &ScanScheduler{
		store:             options.Store,
		logger:            logger,
		now:               now,
		schedulerInterval: schedulerInterval,
		defaultInterval:   defaultInterval,
		stagger:           stagger,
	}, nil
}

func (s *ScanScheduler) Run(ctx context.Context) error {
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
	enqueued := 0

	for _, bucket := range buckets {
		active, err := s.store.JobRuns().HasActiveJobRun(ctx, storage.HasActiveJobRunParams{
			Type:       storage.JobTypeScanBucket,
			TargetType: "bucket",
			TargetID:   bucket.ID,
		})
		if err != nil {
			return enqueued, err
		}

		lastFinished, err := s.store.JobRuns().LastSucceededJobRunFinishedAt(ctx, storage.LastSucceededJobRunFinishedAtParams{
			Type:       storage.JobTypeScanBucket,
			TargetType: "bucket",
			TargetID:   bucket.ID,
		})
		if err != nil {
			return enqueued, err
		}

		decision := DecideScan(bucket, lastFinished, now, active, s.defaultInterval)
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

		if s.stagger > 0 {
			select {
			case <-ctx.Done():
				return enqueued, ctx.Err()
			case <-time.After(s.stagger):
			}
		}
	}

	return enqueued, nil
}
