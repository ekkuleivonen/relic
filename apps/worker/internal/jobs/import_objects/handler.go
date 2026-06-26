package import_objects

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
		return nil, fmt.Errorf("create import objects handler: storage store is required")
	}
	if options.Secrets == nil {
		return nil, fmt.Errorf("create import objects handler: secrets manager is required")
	}
	if options.Factory == nil {
		return nil, fmt.Errorf("create import objects handler: upstream client factory is required")
	}

	return &Handler{store: options.Store, secrets: options.Secrets, factory: options.Factory}, nil
}

func (h *Handler) Type() storage.JobType {
	return storage.JobTypeImportObjects
}

func (h *Handler) Handle(ctx context.Context, run storage.JobRun) (storage.JobRunPayload, error) {
	var input jobs.ObjectMutationInput
	if err := jobs.DecodePayload(run.Input, &input); err != nil {
		return nil, err
	}
	if input.BucketID == "" {
		return nil, fmt.Errorf("import_objects job %q is missing bucket_id", run.ID)
	}

	bucket, err := h.store.Buckets().GetBucket(ctx, input.BucketID)
	if err != nil {
		return nil, err
	}
	client, err := h.clientForBucket(ctx, bucket)
	if err != nil {
		return nil, err
	}

	return jobs.ExecuteObjectMutation(ctx, jobs.ExecuteObjectMutationOptions{
		Store:          h.store,
		Run:            run,
		Bucket:         bucket,
		Client:         client,
		Objects:        input.Objects,
		ProgressAction: "import_objects",
		ResultCountKey: "objects_imported",
	})
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
