package sync_bucket

import (
	"context"
	"fmt"
	"time"

	"github.com/ekkuleivonen/relic/packages/secrets"
	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
)

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

	seenAt := time.Now().UTC()
	objectsSeen := 0
	continuationToken := ""
	marker := ""

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
			attributes := s3compat.AttributesFromListedObject(listedObject)
			if _, err := h.store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
				BucketID:   bucket.ID,
				Key:        listedObject.Key,
				Attributes: attributes,
				AttributeProvenance: storage.ObjectAttributeProvenance{
					"upstream": run.ID,
				},
				SeenAt: &seenAt,
			}); err != nil {
				return nil, err
			}
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

	objectsDeleted, err := h.store.Objects().DeleteObjectsNotSeenSince(ctx, storage.DeleteObjectsNotSeenSinceParams{
		BucketID: bucket.ID,
		Prefix:   bucket.Prefix,
		SeenAt:   seenAt,
	})
	if err != nil {
		return nil, err
	}

	return storage.JobRunPayload{
		"phase":           "listed",
		"bucket_id":       bucket.ID,
		"objects_seen":    objectsSeen,
		"objects_deleted": int(objectsDeleted),
	}, nil
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
