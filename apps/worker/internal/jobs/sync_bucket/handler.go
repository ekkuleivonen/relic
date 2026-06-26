package sync_bucket

import (
	"context"
	"fmt"
	"time"

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
	bucketID, err := BucketID(run)
	if err != nil {
		return nil, err
	}

	bucket, err := h.store.Buckets().GetBucket(ctx, bucketID)
	if err != nil {
		return nil, err
	}

	client, err := h.clientForBucket(ctx, bucket)
	if err != nil {
		return nil, err
	}

	objectsSeen := 0
	continuationToken := ""
	marker := ""
	upstreamObjects := map[string]s3compat.ListedObject{}

	for {
		page, err := client.ListObjects(ctx, s3compat.ListObjectsInput{
			Bucket:            bucket.BucketName,
			Prefix:            bucket.Prefix,
			ContinuationToken: continuationToken,
			Marker:            marker,
		})
		if err != nil {
			return nil, err
		}

		for _, listedObject := range page.Objects {
			upstreamObjects[listedObject.Key] = listedObject
			objectsSeen++
		}

		if _, err := h.store.JobRuns().UpdateJobRunProgress(ctx, storage.UpdateJobRunProgressParams{
			ID: run.ID,
			Progress: storage.JobRunPayload{
				"phase":        "listed",
				"objects_seen": objectsSeen,
			},
		}); err != nil {
			return nil, err
		}

		if !page.IsTruncated {
			break
		}
		continuationToken = page.NextContinuationToken
		marker = page.NextMarker
		if continuationToken == "" && marker == "" {
			return nil, fmt.Errorf("sync bucket %q: truncated page did not include a continuation token or marker", bucket.ID)
		}
	}

	localObjects, err := h.store.Objects().ListObjectsInScope(ctx, storage.ObjectScopeParams{
		BucketID: bucket.ID,
		Prefix:   bucket.Prefix,
	})
	if err != nil {
		return nil, err
	}

	importObjects, refreshObjects, removeObjects := planObjectMutations(upstreamObjects, localObjects)
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

	return storage.JobRunPayload{
		"phase":                 "planned",
		"bucket_id":             bucket.ID,
		"objects_seen":          objectsSeen,
		"import_objects_count":  len(importObjects),
		"refresh_objects_count": len(refreshObjects),
		"remove_objects_count":  len(removeObjects),
		"child_job_ids": map[string]any{
			"import_objects":  importJobIDs,
			"refresh_objects": refreshJobIDs,
			"remove_objects":  removeJobIDs,
		},
	}, nil
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

func planObjectMutations(upstreamObjects map[string]s3compat.ListedObject, localObjects []storage.Object) ([]jobs.ObjectEvidence, []jobs.ObjectEvidence, []jobs.ObjectEvidence) {
	localByKey := map[string]storage.Object{}
	for _, object := range localObjects {
		localByKey[object.Key] = object
	}

	importObjects := []jobs.ObjectEvidence{}
	refreshObjects := []jobs.ObjectEvidence{}
	for key, upstreamObject := range upstreamObjects {
		evidence := objectEvidenceFromListedObject(upstreamObject)
		localObject, exists := localByKey[key]
		if !exists {
			importObjects = append(importObjects, evidence)
			continue
		}
		evidence.ID = localObject.ID
		if objectChanged(upstreamObject, localObject) {
			refreshObjects = append(refreshObjects, evidence)
		}
	}

	removeObjects := []jobs.ObjectEvidence{}
	for key, localObject := range localByKey {
		if _, exists := upstreamObjects[key]; exists {
			continue
		}
		removeObjects = append(removeObjects, jobs.ObjectEvidence{
			ID:  localObject.ID,
			Key: localObject.Key,
		})
	}

	return importObjects, refreshObjects, removeObjects
}

func objectEvidenceFromListedObject(object s3compat.ListedObject) jobs.ObjectEvidence {
	return jobs.ObjectEvidence{
		Key:          object.Key,
		ETag:         object.ETag,
		Size:         object.Size,
		LastModified: object.LastModified.UTC().Format(time.RFC3339),
		StorageClass: object.StorageClass,
	}
}

func objectChanged(upstreamObject s3compat.ListedObject, localObject storage.Object) bool {
	upstreamAttributes, _ := localObject.Attributes["upstream"].(map[string]any)
	if upstreamAttributes == nil {
		return true
	}

	return upstreamAttributes["etag"] != upstreamObject.ETag ||
		int64Attribute(upstreamAttributes["size"]) != upstreamObject.Size ||
		upstreamAttributes["last_modified"] != upstreamObject.LastModified.UTC().Format(time.RFC3339) ||
		storageClassAttribute(upstreamAttributes) != upstreamObject.StorageClass
}

func int64Attribute(value any) int64 {
	switch typed := value.(type) {
	case int64:
		return typed
	case int:
		return int64(typed)
	case float64:
		return int64(typed)
	default:
		return 0
	}
}

func storageClassAttribute(upstreamAttributes map[string]any) string {
	if value, ok := upstreamAttributes["storage_class"].(string); ok {
		return value
	}
	for _, namespace := range []string{"s3", "gcp"} {
		nested, ok := upstreamAttributes[namespace].(map[string]any)
		if !ok {
			continue
		}
		if value, ok := nested["storage_class"].(string); ok {
			return value
		}
	}

	return ""
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
