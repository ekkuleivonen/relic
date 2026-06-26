package remove_objects

import (
	"context"
	"fmt"

	"github.com/ekkuleivonen/relic/apps/worker/internal/jobs"
	"github.com/ekkuleivonen/relic/packages/storage"
)

type Handler struct {
	store *storage.Store
}

type HandlerOptions struct {
	Store *storage.Store
}

func NewHandler(options HandlerOptions) (*Handler, error) {
	if options.Store == nil {
		return nil, fmt.Errorf("create remove objects handler: storage store is required")
	}

	return &Handler{store: options.Store}, nil
}

func (h *Handler) Type() storage.JobType {
	return storage.JobTypeRemoveObjects
}

func (h *Handler) Handle(ctx context.Context, run storage.JobRun) (storage.JobRunPayload, error) {
	var input jobs.ObjectMutationInput
	if err := jobs.DecodePayload(run.Input, &input); err != nil {
		return nil, err
	}
	if input.BucketID == "" {
		return nil, fmt.Errorf("remove_objects job %q is missing bucket_id", run.ID)
	}

	ids := []string{}
	for _, object := range input.Objects {
		if object.ID != "" {
			ids = append(ids, object.ID)
		}
	}

	deleted, err := h.store.Objects().DeleteObjects(ctx, storage.DeleteObjectsParams{IDs: ids})
	if err != nil {
		return nil, err
	}

	return storage.JobRunPayload{
		"bucket_id":       input.BucketID,
		"objects_deleted": int(deleted),
		"objects_skipped": len(input.Objects) - len(ids),
	}, nil
}
