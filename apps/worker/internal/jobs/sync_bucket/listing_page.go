package sync_bucket

import (
	"context"

	"github.com/elei-io/pithosys/apps/worker/internal/jobs"
	"github.com/elei-io/pithosys/packages/storage"
	"github.com/elei-io/pithosys/packages/upstreams/s3compat"
)

func listedObjectsForKeys(objects []s3compat.ListedObject, keys []string) []s3compat.ListedObject {
	if len(keys) == 0 {
		return nil
	}

	allowed := make(map[string]struct{}, len(keys))
	for _, key := range keys {
		allowed[key] = struct{}{}
	}

	filtered := make([]s3compat.ListedObject, 0, len(keys))
	for _, object := range objects {
		if _, ok := allowed[object.Key]; ok {
			filtered = append(filtered, object)
		}
	}

	return filtered
}

func keysFromListedObjects(objects []s3compat.ListedObject) []string {
	keys := make([]string, 0, len(objects))
	for _, object := range objects {
		keys = append(keys, object.Key)
	}

	return keys
}

func keysFromObjectEvidence(objects []jobs.ObjectEvidence) []string {
	keys := make([]string, 0, len(objects))
	for _, object := range objects {
		keys = append(keys, object.Key)
	}

	return keys
}

func (h *Handler) filterListedObjectsNotInSpill(
	ctx context.Context,
	jobRunID string,
	objects []s3compat.ListedObject,
) ([]s3compat.ListedObject, error) {
	pendingKeys, err := h.store.JobSpill().FilterKeysNotInSpill(ctx, jobRunID, keysFromListedObjects(objects))
	if err != nil {
		return nil, err
	}

	return listedObjectsForKeys(objects, pendingKeys), nil
}

func (h *Handler) processListingPage(
	ctx context.Context,
	run storage.JobRun,
	bucket storage.Bucket,
	state *syncExecutionState,
	page jobs.ListObjectsPageProgress,
) error {
	if len(page.PageObjects) == 0 {
		return h.updateProgress(ctx, run.ID, listingProgressFields(page.Checkpoint, page.ListingComplete, state.planCounts))
	}

	pendingObjects, err := h.filterListedObjectsNotInSpill(ctx, run.ID, page.PageObjects)
	if err != nil {
		return err
	}
	if len(pendingObjects) > 0 {
		pageKeys := keysFromListedObjects(pendingObjects)
		localObjects, err := h.store.Objects().GetObjectsByBucketAndKeys(ctx, bucket.ID, pageKeys)
		if err != nil {
			return err
		}

		importObjects, refreshObjects, _ := jobs.PlanObjectMutationsForListedObjects(pendingObjects, localObjects)
		if err := h.enqueueMutationJobs(ctx, state, run, bucket.ID, storage.JobTypeImportObjects, importObjects); err != nil {
			return err
		}
		if err := h.enqueueMutationJobs(ctx, state, run, bucket.ID, storage.JobTypeRefreshObjects, refreshObjects); err != nil {
			return err
		}

		mutatedKeys := make(map[string]struct{}, len(importObjects)+len(refreshObjects))
		for _, object := range importObjects {
			mutatedKeys[object.Key] = struct{}{}
		}
		for _, object := range refreshObjects {
			mutatedKeys[object.Key] = struct{}{}
		}

		noMutationKeys := make([]string, 0)
		for _, key := range pageKeys {
			if _, ok := mutatedKeys[key]; ok {
				continue
			}
			noMutationKeys = append(noMutationKeys, key)
		}
		if err := h.store.JobSpill().InsertKeys(ctx, run.ID, noMutationKeys); err != nil {
			return err
		}
	}

	return h.updateProgress(ctx, run.ID, listingProgressFields(page.Checkpoint, page.ListingComplete, state.planCounts))
}
