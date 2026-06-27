package sync_bucket

import (
	"context"
	"fmt"

	"github.com/ekkuleivonen/relic/apps/worker/internal/jobs"
	"github.com/ekkuleivonen/relic/packages/secrets"
	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
)

const childJobBatchSize = 100

type Handler struct {
	store   *storage.Store
	secrets secrets.Manager
	factory s3compat.ObjectClientFactory
}

type HandlerOptions struct {
	Store   *storage.Store
	Secrets secrets.Manager
	Factory s3compat.ObjectClientFactory
}

func NewHandler(options HandlerOptions) (*Handler, error) {
	if options.Store == nil {
		return nil, fmt.Errorf("create sync bucket handler: storage store is required")
	}
	if options.Secrets == nil {
		return nil, fmt.Errorf("create sync bucket handler: secrets manager is required")
	}
	if options.Factory == nil {
		return nil, fmt.Errorf("create sync bucket handler: upstream client factory is required")
	}

	return &Handler{
		store:   options.Store,
		secrets: options.Secrets,
		factory: options.Factory,
	}, nil
}

func (h *Handler) Type() storage.JobType {
	return storage.JobTypeSyncBucket
}

func (h *Handler) Handle(ctx context.Context, run storage.JobRun) (storage.JobRunPayload, error) {
	input, err := ParseSyncBucketInput(run)
	if err != nil {
		return nil, err
	}

	bucket, err := h.store.Buckets().GetBucket(ctx, input.BucketID)
	if err != nil {
		return nil, err
	}

	client, err := h.clientForBucket(ctx, bucket)
	if err != nil {
		return nil, err
	}

	listPrefix := EffectiveListPrefix(bucket.Prefix, input.ScopePrefix)
	upstreamObjects := map[string]s3compat.ListedObject{}

	var partitionFilter func(s3compat.ListedObject) bool
	if input.Partition != nil {
		partition := *input.Partition
		partitionFilter = func(object s3compat.ListedObject) bool {
			return KeyMatchesPartition(object.Key, partition)
		}
	}

	_, objectsSeen, err := jobs.ListAllObjects(ctx, jobs.ListAllObjectsOptions{
		Client:      client,
		BucketName:  bucket.BucketName,
		Prefix:      listPrefix,
		BucketLabel: bucket.ID,
		Filter:      partitionFilter,
		OnObject: func(listedObject s3compat.ListedObject) error {
			upstreamObjects[listedObject.Key] = listedObject
			return nil
		},
		OnPage: func(listed int64) error {
			_, err := h.store.JobRuns().UpdateJobRunProgress(ctx, storage.UpdateJobRunProgressParams{
				ID: run.ID,
				Progress: storage.JobRunPayload{
					"phase":        "listed",
					"objects_seen": listed,
				},
			})
			return err
		},
	})
	if err != nil {
		return nil, err
	}

	localObjects, err := collectLocalObjectsInScope(ctx, h.store.Objects(), ObjectScopeParams(bucket.ID, bucket.Prefix, input), input.Partition)
	if err != nil {
		return nil, err
	}

	importObjects, refreshObjects, removeObjects := jobs.PlanObjectMutations(upstreamObjects, localObjects)
	importJobIDs, err := h.createChildJobs(ctx, run, bucket.ID, storage.JobTypeImportObjects, importObjects)
	if err != nil {
		return nil, err
	}
	refreshJobIDs, err := h.createChildJobs(ctx, run, bucket.ID, storage.JobTypeRefreshObjects, refreshObjects)
	if err != nil {
		return nil, err
	}
	removeJobIDs, err := h.createChildJobs(ctx, run, bucket.ID, storage.JobTypeRemoveObjects, removeObjects)
	if err != nil {
		return nil, err
	}

	result := storage.JobRunPayload{
		"phase":                 "planned",
		"bucket_id":             bucket.ID,
		"scope_prefix":          input.ScopePrefix,
		"objects_seen":          objectsSeen,
		"import_objects_count":  len(importObjects),
		"refresh_objects_count": len(refreshObjects),
		"remove_objects_count":  len(removeObjects),
		"child_job_ids": map[string]any{
			"import_objects":  importJobIDs,
			"refresh_objects": refreshJobIDs,
			"remove_objects":  removeJobIDs,
		},
	}
	for key, value := range syncResultScopeFields(input) {
		result[key] = value
	}

	return result, nil
}

func syncResultScopeFields(input SyncBucketInput) storage.JobRunPayload {
	result := storage.JobRunPayload{}
	if input.Partition != nil {
		result["partition"] = map[string]any{
			"scheme":  input.Partition.Scheme,
			"modulus": input.Partition.Modulus,
			"index":   input.Partition.Index,
		}
	}

	return result
}

func (h *Handler) createChildJobs(ctx context.Context, run storage.JobRun, bucketID string, jobType storage.JobType, objects []jobs.ObjectEvidence) ([]string, error) {
	jobIDs := []string{}
	for _, batch := range objectEvidenceBatches(objects, childJobBatchSize) {
		input, err := jobs.PayloadFrom(jobs.ObjectMutationInput{
			BucketID:       bucketID,
			Objects:        batch,
			SourceJobRunID: run.ID,
		})
		if err != nil {
			return nil, err
		}
		childRun, err := h.store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
			Type:            jobType,
			RequestedByType: "job",
			RequestedByID:   run.ID,
			TargetType:      "bucket",
			TargetID:        bucketID,
			Input:           input,
		})
		if err != nil {
			return nil, err
		}
		jobIDs = append(jobIDs, childRun.ID)
	}

	return jobIDs, nil
}

func objectEvidenceBatches(objects []jobs.ObjectEvidence, size int) [][]jobs.ObjectEvidence {
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

func (h *Handler) clientForBucket(ctx context.Context, bucket storage.Bucket) (s3compat.ObjectClient, error) {
	config, err := s3compat.BucketConfigFromStorage(bucket)
	if err != nil {
		return nil, err
	}
	credentialJSON, err := h.secrets.Decrypt(ctx, bucket.EncryptedCredentials)
	if err != nil {
		return nil, err
	}
	credentials, err := s3compat.ParseCredentials(credentialJSON)
	if err != nil {
		return nil, err
	}

	return h.factory.NewClient(ctx, config, credentials)
}

func BucketID(run storage.JobRun) (string, error) {
	if bucketID, ok := run.Input["bucket_id"].(string); ok && bucketID != "" {
		return bucketID, nil
	}
	if run.TargetType == "bucket" && run.TargetID != "" {
		return run.TargetID, nil
	}

	return "", fmt.Errorf("sync_bucket job %q is missing bucket_id", run.ID)
}
