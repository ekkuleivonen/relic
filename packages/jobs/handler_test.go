package jobs

import (
	"context"
	"testing"

	"github.com/ekkuleivonen/relic/packages/storage"
)

func TestRegistryRejectsDuplicateHandler(t *testing.T) {
	handler := fakeHandler{jobType: storage.JobTypeSyncBucket}

	_, err := NewRegistry(handler, handler)
	if err == nil {
		t.Fatal("NewRegistry returned nil error, want duplicate handler error")
	}
}

func TestRegistryGet(t *testing.T) {
	handler := fakeHandler{jobType: storage.JobTypeSyncBucket}
	registry, err := NewRegistry(handler)
	if err != nil {
		t.Fatalf("NewRegistry returned error: %v", err)
	}

	got, ok := registry.Get(storage.JobTypeSyncBucket)
	if !ok {
		t.Fatal("Get did not find registered handler")
	}
	if got.Type() != storage.JobTypeSyncBucket {
		t.Fatalf("got handler type = %q, want %q", got.Type(), storage.JobTypeSyncBucket)
	}
}

type fakeHandler struct {
	jobType storage.JobType
}

func (h fakeHandler) Type() storage.JobType {
	return h.jobType
}

func (h fakeHandler) Handle(context.Context, storage.JobRun) (storage.JobRunPayload, error) {
	return storage.JobRunPayload{}, nil
}
