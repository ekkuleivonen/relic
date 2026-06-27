package scan_bucket

import (
	"context"
	"fmt"
	"time"

	"github.com/ekkuleivonen/relic/apps/worker/internal/jobs"
	"github.com/ekkuleivonen/relic/packages/secrets"
	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
	"github.com/ekkuleivonen/relic/packages/verification"
)

type Handler struct {
	store   *storage.Store
	secrets secrets.Manager
	factory s3compat.ObjectClientFactory
	now     func() time.Time
	modulus uint32
	budget  ScanBudgetConfig
}

type HandlerOptions struct {
	Store   *storage.Store
	Secrets secrets.Manager
	Factory s3compat.ObjectClientFactory
	Now     func() time.Time
	Modulus uint32
	Budget  ScanBudgetConfig
}

func NewHandler(options HandlerOptions) (*Handler, error) {
	if options.Store == nil {
		return nil, fmt.Errorf("create scan bucket handler: storage store is required")
	}
	if options.Secrets == nil {
		return nil, fmt.Errorf("create scan bucket handler: secrets manager is required")
	}
	if options.Factory == nil {
		return nil, fmt.Errorf("create scan bucket handler: upstream client factory is required")
	}

	now := options.Now
	if now == nil {
		now = time.Now
	}
	modulus := options.Modulus
	if modulus == 0 {
		modulus = verification.DefaultModulus
	}

	return &Handler{
		store:   options.Store,
		secrets: options.Secrets,
		factory: options.Factory,
		now:     now,
		modulus: modulus,
		budget:  options.Budget,
	}, nil
}

func (h *Handler) Type() storage.JobType {
	return storage.JobTypeScanBucket
}

func (h *Handler) Handle(ctx context.Context, run storage.JobRun) (storage.JobRunPayload, error) {
	input, err := ParseScanInput(run)
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

	scope := ObjectScopeParams(bucket.ID, bucket.Prefix, input)
	objectCount, err := h.store.Objects().CountObjectsInScope(ctx, scope)
	if err != nil {
		return nil, err
	}

	epoch := verification.DailyEpoch(h.now())
	sampled := verification.SamplePartitions(h.modulus, objectCount, epoch)
	if err := h.updateProgress(ctx, run.ID, "sampling_partitions", map[string]any{
		"partitions_sampled": len(sampled),
		"object_count":       objectCount,
	}); err != nil {
		return nil, err
	}

	localAccumulators := verification.NewPartitionAccumulators(h.modulus)
	if err := h.store.Objects().StreamObjectsInScope(ctx, scope, func(object storage.Object) error {
		evidence := jobs.ListingEvidenceFromLocalObject(object)
		localAccumulators.AddKey(object.Key, evidence.Size)
		return nil
	}); err != nil {
		return nil, err
	}

	upstreamAccumulators := verification.NewPartitionAccumulators(h.modulus)
	budget := NewScanBudget(h.budget, h.now(), h.now)
	listPrefix := scope.Prefix
	listingComplete, objectsListed, err := jobs.ListAllObjects(ctx, jobs.ListAllObjectsOptions{
		Client:      client,
		BucketName:  bucket.BucketName,
		Prefix:      listPrefix,
		BucketLabel: bucket.BucketName,
		Budget:      budget,
		OnObject: func(object s3compat.ListedObject) error {
			upstreamAccumulators.AddKey(object.Key, object.Size)
			return nil
		},
	})
	if err != nil {
		return nil, err
	}
	if err := h.updateProgress(ctx, run.ID, "listing_upstream", map[string]any{
		"objects_listed":        objectsListed,
		"listing_pass_complete": listingComplete,
	}); err != nil {
		return nil, err
	}

	if err := h.updateProgress(ctx, run.ID, "evaluating", nil); err != nil {
		return nil, err
	}

	mismatched := []string{}
	partitionsScanned := 0
	syncJobIDs := []string{}

	for _, partition := range sampled {
		localFingerprint := localAccumulators.Snapshot(partition.Index)
		upstreamFingerprint := upstreamAccumulators.Snapshot(partition.Index)
		if localFingerprint.Count == 0 && upstreamFingerprint.Count == 0 {
			continue
		}

		partitionsScanned++
		if !listingComplete {
			continue
		}

		compareResult := verification.CompareFingerprints(localFingerprint, upstreamFingerprint)
		if compareResult.Match {
			continue
		}

		mismatched = append(mismatched, partition.ID())
	}

	if len(mismatched) > 0 {
		if err := h.updateProgress(ctx, run.ID, "escalating", map[string]any{
			"partitions_mismatched": len(mismatched),
		}); err != nil {
			return nil, err
		}
	}

	for _, partitionID := range mismatched {
		partition, err := verification.ParsePartitionID(partitionID)
		if err != nil {
			return nil, err
		}
		childRun, err := h.createPartitionSyncJob(ctx, run, bucket.ID, input.ScopePrefix, partition)
		if err != nil {
			return nil, err
		}
		syncJobIDs = append(syncJobIDs, childRun.ID)
	}

	result := storage.JobRunPayload{
		"phase":                 "completed",
		"bucket_id":             bucket.ID,
		"scope":                 map[string]any{"prefix": input.ScopePrefix},
		"partition_modulus":     h.modulus,
		"partitions_sampled":    len(sampled),
		"partitions_scanned":    partitionsScanned,
		"partitions_mismatched": mismatched,
		"listing_pass_complete": listingComplete,
		"objects_listed":        objectsListed,
		"child_job_ids": map[string]any{
			"sync_bucket": syncJobIDs,
		},
	}

	if listingComplete && len(mismatched) == 0 {
		result["status"] = "healthy"
	}
	if len(mismatched) > 0 {
		result["status"] = "needs_sync"
	}

	return result, nil
}

func (h *Handler) createPartitionSyncJob(
	ctx context.Context,
	run storage.JobRun,
	bucketID string,
	scopePrefix string,
	partition verification.Partition,
) (storage.JobRun, error) {
	return h.store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:            storage.JobTypeSyncBucket,
		RequestedByType: "job",
		RequestedByID:   run.ID,
		TargetType:      "bucket",
		TargetID:        bucketID,
		Input: storage.JobRunPayload{
			"bucket_id":         bucketID,
			"scope_prefix":      scopePrefix,
			"source_job_run_id": run.ID,
			"partition": map[string]any{
				"scheme":  partition.Scheme,
				"modulus": partition.Modulus,
				"index":   partition.Index,
			},
		},
	})
}

func (h *Handler) updateProgress(ctx context.Context, runID string, phase string, fields map[string]any) error {
	progress := storage.JobRunPayload{
		"phase": phase,
	}
	for key, value := range fields {
		progress[key] = value
	}

	_, err := h.store.JobRuns().UpdateJobRunProgress(ctx, storage.UpdateJobRunProgressParams{
		ID:       runID,
		Progress: progress,
	})

	return err
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
