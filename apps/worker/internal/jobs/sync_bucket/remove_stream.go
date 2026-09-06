package sync_bucket

import (
	"context"

	"github.com/elei-io/pithosys/apps/worker/internal/jobs"
	"github.com/elei-io/pithosys/packages/storage"
	"github.com/elei-io/pithosys/packages/verification"
)

func (h *Handler) streamAndEnqueueRemoveObjects(
	ctx context.Context,
	state *syncExecutionState,
	run storage.JobRun,
	bucketID string,
	scope storage.ObjectScopeParams,
	partition *verification.Partition,
) error {
	batch := make([]jobs.ObjectEvidence, 0, childJobBatchSize)
	flush := func() error {
		if len(batch) == 0 {
			return nil
		}
		if err := h.enqueueMutationJobs(ctx, state, run, bucketID, storage.JobTypeRemoveObjects, batch); err != nil {
			return err
		}
		batch = batch[:0]
		return nil
	}

	err := h.store.JobSpill().StreamObjectsInScopeMissingFromSpill(ctx, run.ID, scope, func(object storage.Object) error {
		if partition != nil && !KeyMatchesPartition(object.Key, *partition) {
			return nil
		}
		batch = append(batch, jobs.ObjectEvidence{
			ID:  object.ID,
			Key: object.Key,
		})
		if len(batch) >= childJobBatchSize {
			return flush()
		}
		return nil
	})
	if err != nil {
		return err
	}

	return flush()
}
