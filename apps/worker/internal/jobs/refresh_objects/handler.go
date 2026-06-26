package refresh_objects

import (
	"context"
	"fmt"

	"github.com/ekkuleivonen/relic/apps/worker/internal/jobs"
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
		return nil, fmt.Errorf("create refresh objects handler: storage store is required")
	}
	if options.Secrets == nil {
		return nil, fmt.Errorf("create refresh objects handler: secrets manager is required")
	}
	if options.Factory == nil {
		return nil, fmt.Errorf("create refresh objects handler: upstream client factory is required")
	}

	return &Handler{store: options.Store, secrets: options.Secrets, factory: options.Factory}, nil
}

func (h *Handler) Type() storage.JobType {
	return storage.JobTypeRefreshObjects
}

func (h *Handler) Handle(ctx context.Context, run storage.JobRun) (storage.JobRunPayload, error) {
	var input jobs.ObjectMutationInput
	if err := jobs.DecodePayload(run.Input, &input); err != nil {
		return nil, err
	}
	if input.BucketID == "" {
		return nil, fmt.Errorf("refresh_objects job %q is missing bucket_id", run.ID)
	}

	bucket, err := h.store.Buckets().GetBucket(ctx, input.BucketID)
	if err != nil {
		return nil, err
	}
	client, err := h.clientForBucket(ctx, bucket)
	if err != nil {
		return nil, err
	}

	refreshed := 0
	for _, object := range input.Objects {
		attributes, err := client.HeadObject(ctx, s3compat.HeadObjectInput{
			Bucket:    bucket.BucketName,
			Key:       object.Key,
			VersionID: object.VersionID,
		})
		if err != nil {
			return nil, err
		}
		attributes = jobs.AttributesWithEvidence(attributes, object)
		if _, err := h.store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
			BucketID:   bucket.ID,
			Key:        object.Key,
			VersionID:  object.VersionID,
			Attributes: attributes,
			AttributeProvenance: storage.ObjectAttributeProvenance{
				"upstream": run.ID,
			},
		}); err != nil {
			return nil, err
		}
		refreshed++
	}

	return storage.JobRunPayload{
		"bucket_id":         bucket.ID,
		"objects_refreshed": refreshed,
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
