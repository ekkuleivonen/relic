package sync_bucket

import (
	"context"
	"errors"
	"fmt"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/ekkuleivonen/relic/apps/worker/internal/jobs"
	importobjects "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/import_objects"
	refreshobjects "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/refresh_objects"
	removeobjects "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/remove_objects"
	"github.com/ekkuleivonen/relic/packages/db"
	"github.com/ekkuleivonen/relic/packages/secrets"
	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/testdb"
	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
	"github.com/ekkuleivonen/relic/packages/verification"
)

var (
	migrateTestStoreOnce sync.Once
	migrateTestStoreErr  error
)

func TestHandlerPlansImportJobsForMissingObjects(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "photos/")
	run := createSyncRun(t, ctx, store, bucket.ID)
	listedAt := time.Now().UTC()
	client := &fakeObjectClient{
		page: s3compat.ObjectPage{
			Objects: []s3compat.ListedObject{
				{
					Key:          "photos/a.jpg",
					ETag:         "\"abc123\"",
					Size:         123,
					LastModified: listedAt,
					StorageClass: "STANDARD",
				},
				{
					Key:          "photos/b.jpg",
					ETag:         "\"def456\"",
					Size:         456,
					LastModified: listedAt.Add(time.Minute),
					StorageClass: "STANDARD",
				},
			},
		},
	}
	factory := &fakeObjectClientFactory{client: client}
	handler, err := newTestHandler(store, factory)
	if err != nil {
		t.Fatalf("NewHandler returned error: %v", err)
	}

	result, err := handler.Handle(ctx, run)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}

	if result["objects_seen"] != 2 {
		t.Fatalf("objects_seen result = %#v, want 2", result["objects_seen"])
	}
	if result["import_objects_count"] != 2 {
		t.Fatalf("import count = %#v, want 2", result["import_objects_count"])
	}
	if len(client.listInputs) != 1 {
		t.Fatalf("list calls = %d, want 1", len(client.listInputs))
	}
	if client.listInputs[0].Bucket != bucket.BucketName {
		t.Fatalf("list bucket = %q, want %q", client.listInputs[0].Bucket, bucket.BucketName)
	}
	if client.listInputs[0].Prefix != bucket.Prefix {
		t.Fatalf("list prefix = %q, want %q", client.listInputs[0].Prefix, bucket.Prefix)
	}
	if len(factory.configs) != 1 {
		t.Fatalf("factory calls = %d, want 1", len(factory.configs))
	}
	if factory.configs[0].BucketName != bucket.BucketName {
		t.Fatalf("factory bucket = %q, want %q", factory.configs[0].BucketName, bucket.BucketName)
	}
	if factory.credentials[0].AccessKeyID != "access-key" {
		t.Fatalf("factory access key = %q, want access-key", factory.credentials[0].AccessKeyID)
	}

	children, err := store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		Type:     storage.JobTypeImportObjects,
		TargetID: bucket.ID,
		Limit:    10,
	})
	if err != nil {
		t.Fatalf("ListJobRuns returned error: %v", err)
	}
	if len(children) != 1 {
		t.Fatalf("import child count = %d, want 1", len(children))
	}
	var input jobs.ObjectMutationInput
	if err := jobs.DecodePayload(children[0].Input, &input); err != nil {
		t.Fatalf("DecodePayload returned error: %v", err)
	}
	if len(input.Objects) != 2 {
		t.Fatalf("import input objects = %d, want 2", len(input.Objects))
	}
	if !objectEvidenceContainsKey(input.Objects, "photos/a.jpg") || !objectEvidenceContainsKey(input.Objects, "photos/b.jpg") {
		t.Fatalf("import input objects = %#v, want photos/a.jpg and photos/b.jpg", input.Objects)
	}

	progressed, err := store.JobRuns().GetJobRun(ctx, run.ID)
	if err != nil {
		t.Fatalf("GetJobRun returned error: %v", err)
	}
	if progressed.Progress["phase"] != "listed" {
		t.Fatalf("progress phase = %#v, want listed", progressed.Progress["phase"])
	}
	if progressed.Progress["objects_seen"] != float64(2) {
		t.Fatalf("progress objects_seen = %#v, want 2", progressed.Progress["objects_seen"])
	}
}

func TestHandlerPlansRemoveJobsForMissingRemoteObjects(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "photos/")
	run := createSyncRun(t, ctx, store, bucket.ID)
	oldSeenAt := time.Now().Add(-time.Hour).UTC()
	stale, err := store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "photos/stale.jpg",
		SeenAt:   &oldSeenAt,
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}
	client := &fakeObjectClient{
		page: s3compat.ObjectPage{
			Objects: []s3compat.ListedObject{
				{
					Key:          "photos/current.jpg",
					ETag:         "\"abc123\"",
					Size:         123,
					LastModified: time.Now().UTC(),
					StorageClass: "STANDARD",
				},
			},
		},
	}
	handler, err := newTestHandler(store, &fakeObjectClientFactory{client: client})
	if err != nil {
		t.Fatalf("newTestHandler returned error: %v", err)
	}

	result, err := handler.Handle(ctx, run)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}

	if result["remove_objects_count"] != 1 {
		t.Fatalf("remove count = %#v, want 1", result["remove_objects_count"])
	}
	if _, err := store.Objects().GetObject(ctx, stale.ID); err != nil {
		t.Fatalf("stale object should remain for remove_objects child, got error: %v", err)
	}
	children, err := store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		Type:     storage.JobTypeRemoveObjects,
		TargetID: bucket.ID,
		Limit:    10,
	})
	if err != nil {
		t.Fatalf("ListJobRuns returned error: %v", err)
	}
	if len(children) != 1 {
		t.Fatalf("remove child count = %d, want 1", len(children))
	}
	var input jobs.ObjectMutationInput
	if err := jobs.DecodePayload(children[0].Input, &input); err != nil {
		t.Fatalf("DecodePayload returned error: %v", err)
	}
	if len(input.Objects) != 1 || input.Objects[0].ID != stale.ID {
		t.Fatalf("remove input objects = %#v, want stale ID %q", input.Objects, stale.ID)
	}
}

func TestHandlerPlansRefreshJobsForChangedObjects(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "photos/")
	run := createSyncRun(t, ctx, store, bucket.ID)
	existing, err := store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "photos/changed.jpg",
		Attributes: storage.ObjectAttributes{
			"upstream": map[string]any{
				"etag":          "\"old\"",
				"size":          123,
				"last_modified": "2026-06-26T00:00:00Z",
				"s3": map[string]any{
					"storage_class": "STANDARD",
				},
			},
		},
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}
	client := &fakeObjectClient{
		page: s3compat.ObjectPage{
			Objects: []s3compat.ListedObject{
				{
					Key:          "photos/changed.jpg",
					ETag:         "\"new\"",
					Size:         123,
					LastModified: time.Date(2026, 6, 26, 0, 0, 0, 0, time.UTC),
					StorageClass: "STANDARD",
				},
			},
		},
	}
	handler, err := newTestHandler(store, &fakeObjectClientFactory{client: client})
	if err != nil {
		t.Fatalf("newTestHandler returned error: %v", err)
	}

	result, err := handler.Handle(ctx, run)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if result["refresh_objects_count"] != 1 {
		t.Fatalf("refresh count = %#v, want 1", result["refresh_objects_count"])
	}
	children, err := store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		Type:     storage.JobTypeRefreshObjects,
		TargetID: bucket.ID,
		Limit:    10,
	})
	if err != nil {
		t.Fatalf("ListJobRuns returned error: %v", err)
	}
	if len(children) != 1 {
		t.Fatalf("refresh child count = %d, want 1", len(children))
	}
	var input jobs.ObjectMutationInput
	if err := jobs.DecodePayload(children[0].Input, &input); err != nil {
		t.Fatalf("DecodePayload returned error: %v", err)
	}
	if len(input.Objects) != 1 || input.Objects[0].ID != existing.ID {
		t.Fatalf("refresh input objects = %#v, want existing ID %q", input.Objects, existing.ID)
	}
}

func TestHandlerDoesNotRefreshWhenHeadAttributesMatchListing(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "photos/")
	run := createSyncRun(t, ctx, store, bucket.ID)
	lastModified := time.Date(2026, 6, 26, 0, 0, 0, 0, time.UTC)
	_, err := store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "photos/current.jpg",
		Attributes: storage.ObjectAttributes{
			"upstream": map[string]any{
				"etag":          "\"abc123\"",
				"size":          123,
				"last_modified": lastModified.Format(time.RFC3339),
				"s3": map[string]any{
					"storage_class": "STANDARD",
				},
			},
		},
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}
	client := &fakeObjectClient{
		page: s3compat.ObjectPage{
			Objects: []s3compat.ListedObject{
				{
					Key:          "photos/current.jpg",
					ETag:         "\"abc123\"",
					Size:         123,
					LastModified: lastModified,
					StorageClass: "STANDARD",
				},
			},
		},
	}
	handler, err := newTestHandler(store, &fakeObjectClientFactory{client: client})
	if err != nil {
		t.Fatalf("newTestHandler returned error: %v", err)
	}

	result, err := handler.Handle(ctx, run)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if result["refresh_objects_count"] != 0 {
		t.Fatalf("refresh count = %#v, want 0", result["refresh_objects_count"])
	}
}

func TestSyncChainConvergesAcrossRepeatedChanges(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "photos/")
	lastModified := time.Date(2026, 6, 26, 0, 0, 0, 0, time.UTC)
	client := &fakeObjectClient{
		page: s3compat.ObjectPage{
			Objects: []s3compat.ListedObject{
				listedObject("photos/a.jpg", "\"a1\"", 100, lastModified),
				listedObject("photos/b.jpg", "\"b1\"", 200, lastModified),
			},
		},
		headAttributesByKey: map[string]storage.ObjectAttributes{
			"photos/a.jpg": headAttributes("\"a1\"", 100, lastModified),
			"photos/b.jpg": headAttributes("\"b1\"", 200, lastModified),
		},
	}
	factory := &fakeObjectClientFactory{client: client}
	syncHandler, err := newTestHandler(store, factory)
	if err != nil {
		t.Fatalf("newTestHandler returned error: %v", err)
	}
	importHandler := newImportHandler(t, store, factory)
	refreshHandler := newRefreshHandler(t, store, factory)
	removeHandler := newRemoveHandler(t, store)

	firstSync := createSyncRun(t, ctx, store, bucket.ID)
	firstResult, err := syncHandler.Handle(ctx, firstSync)
	if err != nil {
		t.Fatalf("first sync returned error: %v", err)
	}
	assertPlannedCounts(t, firstResult, 2, 0, 0)
	runChildJobs(t, ctx, store, firstSync.ID, storage.JobTypeImportObjects, importHandler.Handle)
	assertObjectCount(t, ctx, store, bucket.ID, 2)

	secondSync := createSyncRun(t, ctx, store, bucket.ID)
	secondResult, err := syncHandler.Handle(ctx, secondSync)
	if err != nil {
		t.Fatalf("second sync returned error: %v", err)
	}
	assertPlannedCounts(t, secondResult, 0, 0, 0)
	assertChildJobCount(t, ctx, store, secondSync.ID, storage.JobTypeImportObjects, 0)
	assertChildJobCount(t, ctx, store, secondSync.ID, storage.JobTypeRefreshObjects, 0)
	assertChildJobCount(t, ctx, store, secondSync.ID, storage.JobTypeRemoveObjects, 0)

	client.page = s3compat.ObjectPage{
		Objects: []s3compat.ListedObject{
			listedObject("photos/a.jpg", "\"a2\"", 100, lastModified),
			listedObject("photos/b.jpg", "\"b1\"", 200, lastModified),
		},
	}
	client.headAttributesByKey["photos/a.jpg"] = headAttributes("\"a2\"", 100, lastModified)
	refreshSync := createSyncRun(t, ctx, store, bucket.ID)
	refreshResult, err := syncHandler.Handle(ctx, refreshSync)
	if err != nil {
		t.Fatalf("refresh sync returned error: %v", err)
	}
	assertPlannedCounts(t, refreshResult, 0, 1, 0)
	runChildJobs(t, ctx, store, refreshSync.ID, storage.JobTypeRefreshObjects, refreshHandler.Handle)

	client.page = s3compat.ObjectPage{
		Objects: []s3compat.ListedObject{
			listedObject("photos/a.jpg", "\"a2\"", 100, lastModified),
		},
	}
	removeSync := createSyncRun(t, ctx, store, bucket.ID)
	removeResult, err := syncHandler.Handle(ctx, removeSync)
	if err != nil {
		t.Fatalf("remove sync returned error: %v", err)
	}
	assertPlannedCounts(t, removeResult, 0, 0, 1)
	runChildJobs(t, ctx, store, removeSync.ID, storage.JobTypeRemoveObjects, removeHandler.Handle)
	assertObjectCount(t, ctx, store, bucket.ID, 1)

	finalSync := createSyncRun(t, ctx, store, bucket.ID)
	finalResult, err := syncHandler.Handle(ctx, finalSync)
	if err != nil {
		t.Fatalf("final sync returned error: %v", err)
	}
	assertPlannedCounts(t, finalResult, 0, 0, 0)
}

func TestHandlerFailsWhenListObjectsFails(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "photos/")
	run := createSyncRun(t, ctx, store, bucket.ID)
	handler, err := newTestHandler(store, &fakeObjectClientFactory{
		client: &fakeObjectClient{err: errors.New("list failed")},
	})
	if err != nil {
		t.Fatalf("newTestHandler returned error: %v", err)
	}

	if _, err := handler.Handle(ctx, run); err == nil {
		t.Fatal("Handle returned nil error, want list error")
	}
	assertChildJobCount(t, ctx, store, run.ID, storage.JobTypeImportObjects, 0)
}

func TestHandlerFailsWhenListObjectsFailsMidPage(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "photos/")
	run := createSyncRun(t, ctx, store, bucket.ID)
	handler, err := newTestHandler(store, &fakeObjectClientFactory{
		client: &fakeObjectClient{
			pages: []s3compat.ObjectPage{
				{
					Objects:               []s3compat.ListedObject{listedObject("photos/a.jpg", "\"a1\"", 100, time.Now().UTC())},
					IsTruncated:           true,
					NextContinuationToken: "next-page",
				},
			},
			errs: []error{nil, errors.New("second page failed")},
		},
	})
	if err != nil {
		t.Fatalf("newTestHandler returned error: %v", err)
	}

	if _, err := handler.Handle(ctx, run); err == nil {
		t.Fatal("Handle returned nil error, want second page error")
	}
	assertChildJobCount(t, ctx, store, run.ID, storage.JobTypeImportObjects, 0)
}

func TestHandlerFailsWhenTruncatedPageHasNoCursor(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "photos/")
	run := createSyncRun(t, ctx, store, bucket.ID)
	handler, err := newTestHandler(store, &fakeObjectClientFactory{
		client: &fakeObjectClient{
			page: s3compat.ObjectPage{
				Objects:     []s3compat.ListedObject{listedObject("photos/a.jpg", "\"a1\"", 100, time.Now().UTC())},
				IsTruncated: true,
			},
		},
	})
	if err != nil {
		t.Fatalf("newTestHandler returned error: %v", err)
	}

	if _, err := handler.Handle(ctx, run); err == nil {
		t.Fatal("Handle returned nil error, want missing cursor error")
	}
	assertChildJobCount(t, ctx, store, run.ID, storage.JobTypeImportObjects, 0)
}

func TestHandlerScopesListPrefixToEffectiveScope(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "raw/")
	run := createSyncRunWithInput(t, ctx, store, bucket.ID, storage.JobRunPayload{
		"bucket_id":    bucket.ID,
		"scope_prefix": "batch/",
	})
	client := &fakeObjectClient{page: s3compat.ObjectPage{}}
	handler, err := newTestHandler(store, &fakeObjectClientFactory{client: client})
	if err != nil {
		t.Fatalf("newTestHandler returned error: %v", err)
	}

	if _, err := handler.Handle(ctx, run); err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if len(client.listInputs) != 1 {
		t.Fatalf("list calls = %d, want 1", len(client.listInputs))
	}
	if client.listInputs[0].Prefix != "raw/batch/" {
		t.Fatalf("list prefix = %q, want raw/batch/", client.listInputs[0].Prefix)
	}
}

func TestHandlerPartitionSyncOnlyReconcilesMatchingKeys(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "")
	partition := verification.PartitionFromIndex(42, verification.DefaultModulus)
	keyInPartition := keyForPartitionIndex(t, partition.Index, partition.Modulus)
	keyOutPartition := keyForPartitionIndex(t, 99, partition.Modulus)
	listedAt := time.Now().UTC()

	if _, err := store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      keyOutPartition,
	}); err != nil {
		t.Fatalf("UpsertObject out-of-partition returned error: %v", err)
	}

	client := &fakeObjectClient{
		page: s3compat.ObjectPage{
			Objects: []s3compat.ListedObject{
				listedObject(keyInPartition, "\"in-partition\"", 100, listedAt),
				listedObject(keyOutPartition, "\"out-partition\"", 200, listedAt),
			},
		},
	}
	handler, err := newTestHandler(store, &fakeObjectClientFactory{client: client})
	if err != nil {
		t.Fatalf("newTestHandler returned error: %v", err)
	}

	run := createSyncRunWithInput(t, ctx, store, bucket.ID, storage.JobRunPayload{
		"bucket_id": bucket.ID,
		"partition": map[string]any{
			"scheme":  verification.SchemeHash,
			"modulus": float64(partition.Modulus),
			"index":   float64(partition.Index),
		},
	})
	result, err := handler.Handle(ctx, run)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if result["import_objects_count"] != 1 {
		t.Fatalf("import count = %#v, want 1", result["import_objects_count"])
	}
	if result["remove_objects_count"] != 0 {
		t.Fatalf("remove count = %#v, want 0", result["remove_objects_count"])
	}

	children, err := store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		Type:     storage.JobTypeImportObjects,
		TargetID: bucket.ID,
		Limit:    10,
	})
	if err != nil {
		t.Fatalf("ListJobRuns returned error: %v", err)
	}
	if len(children) != 1 {
		t.Fatalf("import child count = %d, want 1", len(children))
	}
	var input jobs.ObjectMutationInput
	if err := jobs.DecodePayload(children[0].Input, &input); err != nil {
		t.Fatalf("DecodePayload returned error: %v", err)
	}
	if len(input.Objects) != 1 || input.Objects[0].Key != keyInPartition {
		t.Fatalf("import input objects = %#v, want only %q", input.Objects, keyInPartition)
	}
}

func TestHandlerPartitionSyncRemovesMissingRemoteObjectsInPartition(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "")
	partition := verification.PartitionFromIndex(42, verification.DefaultModulus)
	keyInPartition := keyForPartitionIndex(t, partition.Index, partition.Modulus)

	stale, err := store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      keyInPartition,
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}

	client := &fakeObjectClient{page: s3compat.ObjectPage{Objects: []s3compat.ListedObject{}}}
	handler, err := newTestHandler(store, &fakeObjectClientFactory{client: client})
	if err != nil {
		t.Fatalf("newTestHandler returned error: %v", err)
	}

	run := createSyncRunWithInput(t, ctx, store, bucket.ID, storage.JobRunPayload{
		"bucket_id": bucket.ID,
		"partition": map[string]any{
			"scheme":  verification.SchemeHash,
			"modulus": float64(partition.Modulus),
			"index":   float64(partition.Index),
		},
	})
	result, err := handler.Handle(ctx, run)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if result["remove_objects_count"] != 1 {
		t.Fatalf("remove count = %#v, want 1", result["remove_objects_count"])
	}

	children, err := store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		Type:     storage.JobTypeRemoveObjects,
		TargetID: bucket.ID,
		Limit:    10,
	})
	if err != nil {
		t.Fatalf("ListJobRuns returned error: %v", err)
	}
	if len(children) != 1 {
		t.Fatalf("remove child count = %d, want 1", len(children))
	}
	var input jobs.ObjectMutationInput
	if err := jobs.DecodePayload(children[0].Input, &input); err != nil {
		t.Fatalf("DecodePayload returned error: %v", err)
	}
	if len(input.Objects) != 1 || input.Objects[0].ID != stale.ID {
		t.Fatalf("remove input objects = %#v, want stale ID %q", input.Objects, stale.ID)
	}
}

func TestHandlerFailsBeforeListingWithInvalidCredentials(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "photos/")
	run := createSyncRun(t, ctx, store, bucket.ID)
	client := &fakeObjectClient{}
	handler, err := NewHandler(HandlerOptions{
		Store:   store,
		Secrets: fakeSecretsManager{plaintext: []byte(`{"access_key_id":""}`)},
		Factory: &fakeObjectClientFactory{client: client},
	})
	if err != nil {
		t.Fatalf("NewHandler returned error: %v", err)
	}

	if _, err := handler.Handle(ctx, run); err == nil {
		t.Fatal("Handle returned nil error, want credentials error")
	}
	if len(client.listInputs) != 0 {
		t.Fatalf("list calls = %d, want 0", len(client.listInputs))
	}
	assertChildJobCount(t, ctx, store, run.ID, storage.JobTypeImportObjects, 0)
}

func listedObject(key string, etag string, size int64, lastModified time.Time) s3compat.ListedObject {
	return s3compat.ListedObject{
		Key:          key,
		ETag:         etag,
		Size:         size,
		LastModified: lastModified,
		StorageClass: "STANDARD",
	}
}

func headAttributes(etag string, size int64, lastModified time.Time) storage.ObjectAttributes {
	return storage.ObjectAttributes{
		"upstream": map[string]any{
			"etag":          etag,
			"size":          size,
			"last_modified": lastModified.UTC().Format(time.RFC3339),
			"header": map[string]any{
				"content_type": "image/jpeg",
			},
		},
	}
}

func assertPlannedCounts(t *testing.T, result storage.JobRunPayload, imports int, refreshes int, removals int) {
	t.Helper()

	if result["import_objects_count"] != imports {
		t.Fatalf("import count = %#v, want %d", result["import_objects_count"], imports)
	}
	if result["refresh_objects_count"] != refreshes {
		t.Fatalf("refresh count = %#v, want %d", result["refresh_objects_count"], refreshes)
	}
	if result["remove_objects_count"] != removals {
		t.Fatalf("remove count = %#v, want %d", result["remove_objects_count"], removals)
	}
}

func assertChildJobCount(t *testing.T, ctx context.Context, store *storage.Store, parentRunID string, jobType storage.JobType, want int) {
	t.Helper()

	children, err := childJobs(ctx, store, parentRunID, jobType)
	if err != nil {
		t.Fatalf("childJobs returned error: %v", err)
	}
	if len(children) != want {
		t.Fatalf("%s child count = %d, want %d", jobType, len(children), want)
	}
}

func childJobs(ctx context.Context, store *storage.Store, parentRunID string, jobType storage.JobType) ([]storage.JobRun, error) {
	return store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		Type:            jobType,
		RequestedByType: "job",
		RequestedByID:   parentRunID,
		Limit:           100,
	})
}

func runChildJobs(t *testing.T, ctx context.Context, store *storage.Store, parentRunID string, jobType storage.JobType, handle func(context.Context, storage.JobRun) (storage.JobRunPayload, error)) {
	t.Helper()

	children, err := childJobs(ctx, store, parentRunID, jobType)
	if err != nil {
		t.Fatalf("childJobs returned error: %v", err)
	}
	for _, child := range children {
		if _, err := handle(ctx, child); err != nil {
			t.Fatalf("handle %s child returned error: %v", jobType, err)
		}
	}
}

func assertObjectCount(t *testing.T, ctx context.Context, store *storage.Store, bucketID string, want int) {
	t.Helper()

	objects, err := store.Objects().ListObjectsInScope(ctx, storage.ObjectScopeParams{BucketID: bucketID})
	if err != nil {
		t.Fatalf("ListObjectsInScope returned error: %v", err)
	}
	if len(objects) != want {
		t.Fatalf("object count = %d, want %d", len(objects), want)
	}
}

func objectEvidenceContainsKey(objects []jobs.ObjectEvidence, key string) bool {
	for _, object := range objects {
		if object.Key == key {
			return true
		}
	}

	return false
}

func newImportHandler(t *testing.T, store *storage.Store, factory s3compat.ObjectClientFactory) *importobjects.Handler {
	t.Helper()

	handler, err := importobjects.NewHandler(importobjects.HandlerOptions{
		Store:   store,
		Secrets: testSecretsManager(),
		Factory: factory,
	})
	if err != nil {
		t.Fatalf("import_objects NewHandler returned error: %v", err)
	}

	return handler
}

func newRefreshHandler(t *testing.T, store *storage.Store, factory s3compat.ObjectClientFactory) *refreshobjects.Handler {
	t.Helper()

	handler, err := refreshobjects.NewHandler(refreshobjects.HandlerOptions{
		Store:   store,
		Secrets: testSecretsManager(),
		Factory: factory,
	})
	if err != nil {
		t.Fatalf("refresh_objects NewHandler returned error: %v", err)
	}

	return handler
}

func newRemoveHandler(t *testing.T, store *storage.Store) *removeobjects.Handler {
	t.Helper()

	handler, err := removeobjects.NewHandler(removeobjects.HandlerOptions{Store: store})
	if err != nil {
		t.Fatalf("remove_objects NewHandler returned error: %v", err)
	}

	return handler
}

type fakeObjectClient struct {
	page                s3compat.ObjectPage
	pages               []s3compat.ObjectPage
	err                 error
	errs                []error
	headAttributesByKey map[string]storage.ObjectAttributes
	headErrByKey        map[string]error
	listInputs          []s3compat.ListObjectsInput
	headInputs          []s3compat.HeadObjectInput
}

type fakeObjectClientFactory struct {
	client      s3compat.ObjectClient
	err         error
	configs     []s3compat.BucketConfig
	credentials []s3compat.Credentials
}

func (f *fakeObjectClientFactory) NewClient(ctx context.Context, config s3compat.BucketConfig, credentials s3compat.Credentials) (s3compat.ObjectClient, error) {
	f.configs = append(f.configs, config)
	f.credentials = append(f.credentials, credentials)
	return f.client, f.err
}

type fakeSecretsManager struct {
	plaintext []byte
	err       error
}

func (m fakeSecretsManager) Encrypt(ctx context.Context, plaintext []byte) (secrets.Envelope, error) {
	return secrets.Envelope{}, nil
}

func (m fakeSecretsManager) Decrypt(ctx context.Context, envelope secrets.Envelope) ([]byte, error) {
	return m.plaintext, m.err
}

func newTestHandler(store *storage.Store, factory s3compat.ObjectClientFactory) (*Handler, error) {
	return NewHandler(HandlerOptions{
		Store:   store,
		Secrets: testSecretsManager(),
		Factory: factory,
	})
}

func testSecretsManager() fakeSecretsManager {
	return fakeSecretsManager{
		plaintext: []byte(`{"access_key_id":"access-key","secret_access_key":"secret-key"}`),
	}
}

func (c *fakeObjectClient) ListObjects(ctx context.Context, input s3compat.ListObjectsInput) (s3compat.ObjectPage, error) {
	c.listInputs = append(c.listInputs, input)
	index := len(c.listInputs) - 1
	if index < len(c.errs) && c.errs[index] != nil {
		return s3compat.ObjectPage{}, c.errs[index]
	}
	if c.err != nil {
		return s3compat.ObjectPage{}, c.err
	}
	if len(c.pages) > 0 {
		if index >= len(c.pages) {
			return s3compat.ObjectPage{}, fmt.Errorf("unexpected list page %d", index)
		}
		return c.pages[index], nil
	}
	return c.page, c.err
}

func (c *fakeObjectClient) HeadObject(ctx context.Context, input s3compat.HeadObjectInput) (s3compat.HeadObjectData, error) {
	c.headInputs = append(c.headInputs, input)
	if err := c.headErrByKey[input.Key]; err != nil {
		return s3compat.HeadObjectData{}, err
	}
	if attributes, ok := c.headAttributesByKey[input.Key]; ok {
		return s3compat.HeadObjectDataFromUpstreamAttributes(attributes), nil
	}

	return s3compat.HeadObjectData{Output: &s3.HeadObjectOutput{}}, nil
}

func (c *fakeObjectClient) GetObjectTagging(ctx context.Context, input s3compat.HeadObjectInput) (map[string]string, error) {
	return nil, nil
}

func testStore(t *testing.T, ctx context.Context) (*storage.Store, func()) {
	t.Helper()

	databaseURL := testdb.URL(t, ctx)
	migrationDir, err := filepath.Abs("../../../../../packages/storage/migrations")
	if err != nil {
		t.Fatalf("resolve migration dir: %v", err)
	}
	migrateTestStoreOnce.Do(func() {
		migrateTestStoreErr = testdb.MigrateIfNeeded(t, ctx, databaseURL, "buckets", func() error {
			return storage.RunMigrations(ctx, databaseURL, "file://"+migrationDir)
		})
	})
	if migrateTestStoreErr != nil {
		t.Fatal(testdb.MigrationTimeoutError(migrateTestStoreErr))
	}

	pool, err := db.Connect(ctx, databaseURL)
	if err != nil {
		t.Fatalf("Connect returned error: %v", err)
	}

	store, err := storage.New(pool)
	if err != nil {
		pool.Close()
		t.Fatalf("New returned error: %v", err)
	}
	if err := storage.PrepareTestStore(ctx, store); err != nil {
		pool.Close()
		t.Fatalf("PrepareTestStore returned error: %v", err)
	}

	return store, pool.Close
}

func createTestBucket(t *testing.T, ctx context.Context, store *storage.Store, prefix string) storage.Bucket {
	t.Helper()

	bucket, err := store.Buckets().CreateBucket(ctx, storage.CreateBucketParams{
		Name:        "sync-test-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    storage.BucketUpstreamS3,
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  "sync-test-data",
		Prefix:      prefix,
		EncryptedCredentials: secrets.Envelope{
			KeyID:      "local-dev",
			Algorithm:  secrets.AlgorithmXChaCha20Poly1305,
			Nonce:      []byte("012345678901234567890123"),
			Ciphertext: []byte("encrypted-credentials"),
		},
	})
	if err != nil {
		t.Fatalf("CreateBucket returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.Objects().DeleteObjectsNotSeenSince(context.Background(), storage.DeleteObjectsNotSeenSinceParams{
			BucketID: bucket.ID,
			SeenAt:   time.Now().Add(time.Hour),
		})
		_ = store.Buckets().DeleteBucket(context.Background(), bucket.ID)
	})

	return bucket
}

func createSyncRun(t *testing.T, ctx context.Context, store *storage.Store, bucketID string) storage.JobRun {
	t.Helper()

	return createSyncRunWithInput(t, ctx, store, bucketID, storage.JobRunPayload{
		"bucket_id": bucketID,
	})
}

func createSyncRunWithInput(t *testing.T, ctx context.Context, store *storage.Store, bucketID string, input storage.JobRunPayload) storage.JobRun {
	t.Helper()

	if input == nil {
		input = storage.JobRunPayload{}
	}
	if _, ok := input["bucket_id"]; !ok {
		input["bucket_id"] = bucketID
	}

	run, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       storage.JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   bucketID,
		Input:      input,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}

	return run
}

func keyForPartitionIndex(t *testing.T, index, modulus uint32) string {
	t.Helper()

	for i := range 10_000 {
		key := fmt.Sprintf("objects/%d.dat", i)
		if verification.PartitionIndex(key, modulus) == index {
			return key
		}
	}

	t.Fatalf("could not find key for partition %d/%d", index, modulus)
	return ""
}
