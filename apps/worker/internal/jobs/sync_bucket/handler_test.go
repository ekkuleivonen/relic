package sync_bucket

import (
	"context"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/ekkuleivonen/relic/apps/worker/internal/jobs"
	"github.com/ekkuleivonen/relic/packages/db"
	"github.com/ekkuleivonen/relic/packages/secrets"
	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/testdb"
	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
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
	if input.Objects[0].Key != "photos/a.jpg" {
		t.Fatalf("first import key = %q, want photos/a.jpg", input.Objects[0].Key)
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
				"storage_class": "STANDARD",
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

type fakeObjectClient struct {
	page       s3compat.ObjectPage
	err        error
	listInputs []s3compat.ListObjectsInput
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
		Store: store,
		Secrets: fakeSecretsManager{
			plaintext: []byte(`{"access_key_id":"access-key","secret_access_key":"secret-key"}`),
		},
		Factory: factory,
	})
}

func (c *fakeObjectClient) ListObjects(ctx context.Context, input s3compat.ListObjectsInput) (s3compat.ObjectPage, error) {
	c.listInputs = append(c.listInputs, input)
	return c.page, c.err
}

func (c *fakeObjectClient) HeadObject(ctx context.Context, input s3compat.HeadObjectInput) (storage.ObjectAttributes, error) {
	return storage.ObjectAttributes{}, nil
}

func testStore(t *testing.T, ctx context.Context) (*storage.Store, func()) {
	t.Helper()

	databaseURL := testdb.URL(t, ctx)
	migrationDir, err := filepath.Abs("../../../../../packages/storage/migrations")
	if err != nil {
		t.Fatalf("resolve migration dir: %v", err)
	}
	migrateTestStoreOnce.Do(func() {
		migrateTestStoreErr = storage.RunMigrations(ctx, databaseURL, "file://"+migrationDir)
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

	run, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       storage.JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   bucketID,
		Input: storage.JobRunPayload{
			"bucket_id": bucketID,
		},
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}

	return run
}
