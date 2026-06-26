package sync_bucket

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/ekkuleivonen/relic/packages/db"
	"github.com/ekkuleivonen/relic/packages/secrets"
	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
)

func TestHandlerUpsertsListedObjects(t *testing.T) {
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

	objects, err := store.Objects().ListObjects(ctx, storage.ListObjectsParams{
		BucketID: bucket.ID,
		Prefix:   "photos/",
		Limit:    10,
	})
	if err != nil {
		t.Fatalf("ListObjects returned error: %v", err)
	}
	if len(objects) != 2 {
		t.Fatalf("object count = %d, want 2", len(objects))
	}
	first := objects[0]
	if first.Key != "photos/a.jpg" {
		t.Fatalf("first key = %q, want photos/a.jpg", first.Key)
	}
	upstream, ok := first.Attributes["upstream"].(map[string]any)
	if !ok {
		t.Fatalf("upstream attributes = %#v, want object", first.Attributes["upstream"])
	}
	if upstream["etag"] != "\"abc123\"" {
		t.Fatalf("etag = %#v, want abc123", upstream["etag"])
	}
	if upstream["size"] != float64(123) {
		t.Fatalf("size = %#v, want 123", upstream["size"])
	}
	if first.AttributeProvenance["upstream"] != run.ID {
		t.Fatalf("upstream provenance = %q, want %q", first.AttributeProvenance["upstream"], run.ID)
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

func TestHandlerDeletesStaleObjects(t *testing.T) {
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

	if result["objects_deleted"] != 1 {
		t.Fatalf("objects_deleted result = %#v, want 1", result["objects_deleted"])
	}
	_, err = store.Objects().GetObject(ctx, stale.ID)
	if !errors.Is(err, storage.ErrNotFound) {
		t.Fatalf("stale object error = %v, want %v", err, storage.ErrNotFound)
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

	databaseURL := os.Getenv("DATABASE_URL")
	if databaseURL == "" {
		t.Skip("DATABASE_URL is not set")
	}

	migrationDir, err := filepath.Abs("../../storage/migrations")
	if err != nil {
		t.Fatalf("resolve migration dir: %v", err)
	}
	if err := storage.RunMigrations(ctx, databaseURL, "file://"+migrationDir); err != nil {
		t.Fatalf("RunMigrations returned error: %v", err)
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
