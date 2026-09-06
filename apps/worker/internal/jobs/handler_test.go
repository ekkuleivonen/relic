package jobs

import (
	"context"
	"testing"

	"github.com/elei-io/pithosys/packages/storage"
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

func TestRegistryTypes(t *testing.T) {
	registry, err := NewRegistry(
		fakeHandler{jobType: storage.JobTypeRefreshObjects},
		fakeHandler{jobType: storage.JobTypeImportObjects},
	)
	if err != nil {
		t.Fatalf("NewRegistry returned error: %v", err)
	}

	types := registry.Types()
	if len(types) != 2 {
		t.Fatalf("types length = %d, want 2", len(types))
	}
	if types[0] != storage.JobTypeImportObjects || types[1] != storage.JobTypeRefreshObjects {
		t.Fatalf("types = %#v, want sorted import/refresh types", types)
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
