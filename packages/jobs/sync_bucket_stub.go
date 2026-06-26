package jobs

import (
	"context"
	"fmt"
	"time"

	"github.com/ekkuleivonen/relic/packages/storage"
)

type SyncBucketStubHandler struct {
	store *storage.Store
}

func NewSyncBucketStubHandler(store *storage.Store) (*SyncBucketStubHandler, error) {
	if store == nil {
		return nil, fmt.Errorf("create sync bucket stub handler: storage store is required")
	}

	return &SyncBucketStubHandler{store: store}, nil
}

func (h *SyncBucketStubHandler) Type() storage.JobType {
	return storage.JobTypeSyncBucket
}

func (h *SyncBucketStubHandler) Handle(ctx context.Context, run storage.JobRun) (storage.JobRunPayload, error) {
	bucketID, err := syncBucketID(run)
	if err != nil {
		return nil, err
	}

	bucket, err := h.store.Buckets().GetBucket(ctx, bucketID)
	if err != nil {
		return nil, err
	}

	if _, err := h.store.JobRuns().UpdateJobRunProgress(ctx, storage.UpdateJobRunProgressParams{
		ID: run.ID,
		Progress: storage.JobRunPayload{
			"phase":       "stubbed",
			"bucket_id":   bucket.ID,
			"bucket_name": bucket.BucketName,
			"updated_at":  time.Now().UTC().Format(time.RFC3339Nano),
		},
	}); err != nil {
		return nil, err
	}

	return storage.JobRunPayload{
		"phase":       "stubbed",
		"bucket_id":   bucket.ID,
		"bucket_name": bucket.BucketName,
		"message":     "sync_bucket handler is stubbed",
	}, nil
}

func syncBucketID(run storage.JobRun) (string, error) {
	if bucketID, ok := run.Input["bucket_id"].(string); ok && bucketID != "" {
		return bucketID, nil
	}
	if run.TargetType == "bucket" && run.TargetID != "" {
		return run.TargetID, nil
	}

	return "", fmt.Errorf("sync_bucket job %q is missing bucket_id", run.ID)
}
