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

	state, err := h.loadSyncExecutionState(ctx, run)
	if err != nil {
		return nil, err
	}

	listPrefix := EffectiveListPrefix(bucket.Prefix, input.ScopePrefix)
	scope := ObjectScopeParams(bucket.ID, bucket.Prefix, input)
	checkpoint := listingCheckpointFromProgress(run.Progress)

	var partitionFilter func(s3compat.ListedObject) bool
	if input.Partition != nil {
		partition := *input.Partition
		partitionFilter = func(object s3compat.ListedObject) bool {
			return KeyMatchesPartition(object.Key, partition)
		}
	}

	objectsListed := checkpoint.ObjectsListed
	if !checkpoint.ListingComplete {
		listStart := checkpoint.toListStart()
		listComplete, listed, err := jobs.ListAllObjects(ctx, jobs.ListAllObjectsOptions{
			Client:      client,
			BucketName:  bucket.BucketName,
			Prefix:      listPrefix,
			BucketLabel: bucket.ID,
			Start:       listStart,
			Filter:      partitionFilter,
			OnObject:    func(s3compat.ListedObject) error { return nil },
			OnPage: func(page jobs.ListObjectsPageProgress) error {
				return h.processListingPage(ctx, run, bucket, state, page)
			},
		})
		if err != nil {
			return nil, err
		}
		if !listComplete {
			return nil, fmt.Errorf("sync_bucket job %q: upstream listing incomplete", run.ID)
		}

		objectsListed = listed
		checkpoint.ListingComplete = true
		if err := h.updateProgress(ctx, run.ID, listingProgressFields(jobs.ListCheckpoint{
			ObjectsListed: objectsListed,
		}, true, state.planCounts)); err != nil {
			return nil, err
		}
	}

	if err := h.updateProgress(ctx, run.ID, planningProgressFields(objectsListed, state.planCounts)); err != nil {
		return nil, err
	}

	if err := h.streamAndEnqueueRemoveObjects(ctx, state, run, bucket.ID, scope, input.Partition); err != nil {
		return nil, err
	}

	if err := h.store.JobSpill().DeleteForJobRun(ctx, run.ID); err != nil {
		return nil, err
	}

	result := state.fanOutResult(storage.JobRunPayload{
		"phase":                 "planned",
		"bucket_id":             bucket.ID,
		"scope_prefix":          input.ScopePrefix,
		"objects_seen":          objectsListed,
		"objects_listed":        objectsListed,
		"listing_complete":      true,
		"import_objects_count":  state.planCounts.Import,
		"refresh_objects_count": state.planCounts.Refresh,
		"remove_objects_count":  state.planCounts.Remove,
	})
	for key, value := range syncResultScopeFields(input) {
		result[key] = value
	}

	return result, nil
}

func (h *Handler) enqueueMutationJobs(
	ctx context.Context,
	state *syncExecutionState,
	run storage.JobRun,
	bucketID string,
	jobType storage.JobType,
	objects []jobs.ObjectEvidence,
) error {
	if len(objects) == 0 {
		return nil
	}

	for _, batch := range objectEvidenceBatches(objects, childJobBatchSize) {
		batchKeys := keysFromObjectEvidence(batch)
		var childRun storage.JobRun
		err := h.store.WithTx(ctx, func(ctx context.Context, tx *storage.Tx) error {
			if err := tx.JobSpill().InsertKeys(ctx, run.ID, batchKeys); err != nil {
				return err
			}

			input, err := jobs.PayloadFrom(jobs.ObjectMutationInput{
				BucketID:       bucketID,
				Objects:        batch,
				SourceJobRunID: run.ID,
			})
			if err != nil {
				return err
			}

			created, err := tx.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
				Type:            jobType,
				RequestedByType: "job",
				RequestedByID:   run.ID,
				TargetType:      "bucket",
				TargetID:        bucketID,
				Input:           input,
			})
			if err != nil {
				return err
			}

			childRun = created
			return nil
		})
		if err != nil {
			return err
		}

		state.record(jobType, len(batch), []string{childRun.ID})
	}

	return nil
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

func (h *Handler) updateProgress(ctx context.Context, runID string, fields storage.JobRunPayload) error {
	_, err := h.store.JobRuns().UpdateJobRunProgress(ctx, storage.UpdateJobRunProgressParams{
		ID:       runID,
		Progress: fields,
	})

	return err
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
