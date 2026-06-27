package upstreamprocessor

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/ekkuleivonen/relic/apps/worker/internal/jobs"
	"github.com/ekkuleivonen/relic/packages/storage"
)

const (
	defaultProcessorInterval = 15 * time.Second
	defaultProcessorBatchSize = 100
	defaultMutationJobBatchSize = 100
)

type Processor struct {
	store             *storage.Store
	logger            *slog.Logger
	processorInterval time.Duration
	batchSize         int
	mutationBatchSize int
}

type ProcessorOptions struct {
	Store             *storage.Store
	Logger            *slog.Logger
	ProcessorInterval time.Duration
	BatchSize         int
	MutationBatchSize int
}

func NewProcessor(options ProcessorOptions) (*Processor, error) {
	if options.Store == nil {
		return nil, fmt.Errorf("create upstream event processor: storage store is required")
	}

	logger := options.Logger
	if logger == nil {
		logger = slog.Default()
	}
	processorInterval := options.ProcessorInterval
	if processorInterval <= 0 {
		processorInterval = defaultProcessorInterval
	}
	batchSize := options.BatchSize
	if batchSize <= 0 {
		batchSize = defaultProcessorBatchSize
	}
	mutationBatchSize := options.MutationBatchSize
	if mutationBatchSize <= 0 {
		mutationBatchSize = defaultMutationJobBatchSize
	}

	return &Processor{
		store:             options.Store,
		logger:            logger,
		processorInterval: processorInterval,
		batchSize:         batchSize,
		mutationBatchSize: mutationBatchSize,
	}, nil
}

func (p *Processor) Run(ctx context.Context) error {
	if _, err := p.Tick(ctx); err != nil {
		return err
	}

	ticker := time.NewTicker(p.processorInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
			if _, err := p.Tick(ctx); err != nil {
				return err
			}
		}
	}
}

func (p *Processor) Tick(ctx context.Context) (int, error) {
	var processed int
	err := p.store.WithTx(ctx, func(ctx context.Context, tx *storage.Tx) error {
		events, err := tx.UpstreamEvents().LockPendingEvents(ctx, p.batchSize)
		if err != nil {
			return err
		}
		if len(events) == 0 {
			return nil
		}

		processed, err = p.processLockedEvents(ctx, tx, events)
		return err
	})
	if err != nil {
		return processed, err
	}
	if processed > 0 {
		p.logger.Info("upstream event processor tick complete", "processed", processed)
	}

	return processed, nil
}

func (p *Processor) processLockedEvents(ctx context.Context, tx *storage.Tx, events []storage.UpstreamEvent) (int, error) {
	coalesceInputs := []CoalesceInput{}
	processed := 0

	for _, event := range events {
		bucket, err := tx.Buckets().GetBucket(ctx, event.BucketID)
		if errors.Is(err, storage.ErrNotFound) {
			if err := tx.UpstreamEvents().MarkUpstreamEvent(ctx, storage.MarkUpstreamEventParams{
				ID:           event.ID,
				State:        storage.UpstreamEventStateSkipped,
				ErrorMessage: "bucket_not_found",
			}); err != nil {
				return processed, err
			}
			processed++
			continue
		}
		if err != nil {
			return processed, err
		}

		jobType, ok := JobTypeForEventName(event.EventName)
		if !ok {
			if err := tx.UpstreamEvents().MarkUpstreamEvent(ctx, storage.MarkUpstreamEventParams{
				ID:           event.ID,
				State:        storage.UpstreamEventStateSkipped,
				ErrorMessage: "unsupported_event_name",
			}); err != nil {
				return processed, err
			}
			processed++
			continue
		}

		input := CoalesceInput{
			EventID:  event.ID,
			BucketID: bucket.ID,
			Key:      event.ObjectKey,
			JobType:  jobType,
		}
		if jobType == storage.JobTypeRemoveObjects || jobType == storage.JobTypeRefreshObjects {
			object, err := tx.Objects().GetObjectByBucketAndKey(ctx, bucket.ID, event.ObjectKey)
			if errors.Is(err, storage.ErrNotFound) {
				if err := tx.UpstreamEvents().MarkUpstreamEvent(ctx, storage.MarkUpstreamEventParams{
					ID:           event.ID,
					State:        storage.UpstreamEventStateSkipped,
					ErrorMessage: "object_not_found",
				}); err != nil {
					return processed, err
				}
				processed++
				continue
			}
			if err != nil {
				return processed, err
			}
			input.ObjectID = object.ID
		}

		coalesceInputs = append(coalesceInputs, input)
	}

	for _, group := range GroupMutationsByJob(CoalesceMutations(coalesceInputs)) {
		if err := p.enqueueMutationGroup(ctx, tx, group); err != nil {
			return processed, err
		}
		for _, mutation := range group.Mutations {
			for _, eventID := range mutation.EventIDs {
				if err := tx.UpstreamEvents().MarkUpstreamEvent(ctx, storage.MarkUpstreamEventParams{
					ID:    eventID,
					State: storage.UpstreamEventStateProcessed,
				}); err != nil {
					return processed, err
				}
				processed++
			}
		}
	}

	return processed, nil
}

func (p *Processor) enqueueMutationGroup(ctx context.Context, tx *storage.Tx, group MutationJobGroup) error {
	evidence := make([]jobs.ObjectEvidence, 0, len(group.Mutations))
	for _, mutation := range group.Mutations {
		evidence = append(evidence, jobs.ObjectEvidence{
			ID:  mutation.ObjectID,
			Key: mutation.Key,
		})
	}

	for _, batch := range mutationEvidenceBatches(evidence, p.mutationBatchSize) {
		input, err := jobs.PayloadFrom(jobs.ObjectMutationInput{
			BucketID: group.BucketID,
			Objects:  batch,
		})
		if err != nil {
			return err
		}

		if _, err := tx.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
			Type:            group.JobType,
			RequestedByType: "upstream_event",
			TargetType:      "bucket",
			TargetID:        group.BucketID,
			Input:           input,
		}); err != nil {
			return err
		}
	}

	return nil
}

func mutationEvidenceBatches(objects []jobs.ObjectEvidence, size int) [][]jobs.ObjectEvidence {
	if len(objects) == 0 {
		return nil
	}
	if size <= 0 {
		size = len(objects)
	}

	batches := [][]jobs.ObjectEvidence{}
	for start := 0; start < len(objects); start += size {
		end := start + size
		if end > len(objects) {
			end = len(objects)
		}
		batches = append(batches, objects[start:end])
	}

	return batches
}
