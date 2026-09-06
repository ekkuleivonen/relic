package import_objects

import (
	"context"
	"errors"
	"io"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/elei-io/pithosys/apps/worker/internal/jobs"
	"github.com/elei-io/pithosys/packages/db"
	"github.com/elei-io/pithosys/packages/secrets"
	"github.com/elei-io/pithosys/packages/storage"
	"github.com/elei-io/pithosys/packages/testdb"
	"github.com/elei-io/pithosys/packages/upstreams/s3compat"
)

func TestHandlerImportsObjectsFromHead(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store)
	input, err := jobs.PayloadFrom(jobs.ObjectMutationInput{
		BucketID: bucket.ID,
		Objects: []jobs.ObjectEvidence{{
			Key:          "photos/a.jpg",
			StorageClass: "STANDARD",
		}, {
			Key:          "photos/b.jpg",
			StorageClass: "STANDARD",
		}},
	})
	if err != nil {
		t.Fatalf("PayloadFrom returned error: %v", err)
	}
	run := createJobRun(t, ctx, store, storage.JobTypeImportObjects, bucket.ID, input)
	client := &fakeObjectClient{
		headAttributes: storage.ObjectAttributes{
			"upstream": map[string]any{
				"last_modified": "2026-06-27T12:00:00Z",
				"etag":          "\"abc123\"",
				"size":          int64(123),
				"header": map[string]any{
					"content_type": "image/jpeg",
				},
			},
		},
	}
	handler, err := NewHandler(HandlerOptions{
		Store: store,
		Secrets: fakeSecretsManager{
			plaintext: []byte(`{"access_key_id":"access-key","secret_access_key":"secret-key"}`),
		},
		Factory: &fakeObjectClientFactory{client: client},
	})
	if err != nil {
		t.Fatalf("NewHandler returned error: %v", err)
	}

	result, err := handler.Handle(ctx, run)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if result["objects_imported"] != 2 {
		t.Fatalf("objects_imported = %#v, want 2", result["objects_imported"])
	}
	if len(client.headInputs) != 2 {
		t.Fatalf("head inputs = %d, want 2", len(client.headInputs))
	}

	objects, err := store.Objects().ListObjectsInScope(ctx, storage.ObjectScopeParams{BucketID: bucket.ID})
	if err != nil {
		t.Fatalf("ListObjectsInScope returned error: %v", err)
	}
	if len(objects) != 2 {
		t.Fatalf("object count = %d, want 2", len(objects))
	}
	if objects[0].AttributeProvenance["upstream"] != run.ID {
		t.Fatalf("provenance = %q, want %q", objects[0].AttributeProvenance["upstream"], run.ID)
	}
	upstream, ok := objects[0].Attributes["upstream"].(map[string]any)
	if !ok {
		t.Fatalf("upstream attributes = %#v, want object", objects[0].Attributes["upstream"])
	}
	s3, ok := upstream["s3"].(map[string]any)
	if !ok || s3["storage_class"] != "STANDARD" {
		t.Fatalf("s3.storage_class = %#v, want STANDARD", upstream["s3"])
	}
	header, ok := upstream["header"].(map[string]any)
	if !ok || header["content_type"] != "image/jpeg" {
		t.Fatalf("header = %#v, want content_type image/jpeg", upstream["header"])
	}
	progressed, err := store.JobRuns().GetJobRun(ctx, run.ID)
	if err != nil {
		t.Fatalf("GetJobRun returned error: %v", err)
	}
	if progressed.Progress["phase"] != "upserting" {
		t.Fatalf("progress phase = %#v, want upserting", progressed.Progress["phase"])
	}
	if progressed.Progress["objects_headed"] != float64(2) {
		t.Fatalf("progress objects_headed = %#v, want 2", progressed.Progress["objects_headed"])
	}
	if progressed.Progress["objects_upserted"] != float64(2) {
		t.Fatalf("progress objects_upserted = %#v, want 2", progressed.Progress["objects_upserted"])
	}
}

func TestHandlerFailsWithoutPartialUpsertsWhenHeadFails(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store)
	input, err := jobs.PayloadFrom(jobs.ObjectMutationInput{
		BucketID: bucket.ID,
		Objects: []jobs.ObjectEvidence{
			{Key: "photos/a.jpg"},
			{Key: "photos/b.jpg"},
		},
	})
	if err != nil {
		t.Fatalf("PayloadFrom returned error: %v", err)
	}
	run := createJobRun(t, ctx, store, storage.JobTypeImportObjects, bucket.ID, input)
	handler, err := NewHandler(HandlerOptions{
		Store: store,
		Secrets: fakeSecretsManager{
			plaintext: []byte(`{"access_key_id":"access-key","secret_access_key":"secret-key"}`),
		},
		Factory: &fakeObjectClientFactory{
			client: &fakeObjectClient{
				headAttributes: storage.ObjectAttributes{
					"upstream": map[string]any{"etag": "\"ok\""},
				},
				headErrByKey: map[string]error{
					"photos/b.jpg": errors.New("head failed"),
				},
			},
		},
	})
	if err != nil {
		t.Fatalf("NewHandler returned error: %v", err)
	}

	if _, err := handler.Handle(ctx, run); err == nil {
		t.Fatal("Handle returned nil error, want HEAD error")
	}
	objects, err := store.Objects().ListObjectsInScope(ctx, storage.ObjectScopeParams{BucketID: bucket.ID})
	if err != nil {
		t.Fatalf("ListObjectsInScope returned error: %v", err)
	}
	if len(objects) != 0 {
		t.Fatalf("object count after failed import = %d, want 0", len(objects))
	}
}

func TestHandlerFailsBeforeUpstreamCallWithInvalidCredentials(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store)
	input, err := jobs.PayloadFrom(jobs.ObjectMutationInput{
		BucketID: bucket.ID,
		Objects:  []jobs.ObjectEvidence{{Key: "photos/a.jpg"}},
	})
	if err != nil {
		t.Fatalf("PayloadFrom returned error: %v", err)
	}
	run := createJobRun(t, ctx, store, storage.JobTypeImportObjects, bucket.ID, input)
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
	if len(client.headInputs) != 0 {
		t.Fatalf("head calls = %d, want 0", len(client.headInputs))
	}
}

func TestHandlerFailsCleanlyWhenBucketWasDeleted(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store)
	input, err := jobs.PayloadFrom(jobs.ObjectMutationInput{
		BucketID: bucket.ID,
		Objects:  []jobs.ObjectEvidence{{Key: "photos/a.jpg"}},
	})
	if err != nil {
		t.Fatalf("PayloadFrom returned error: %v", err)
	}
	run := createJobRun(t, ctx, store, storage.JobTypeImportObjects, bucket.ID, input)
	if err := store.Buckets().DeleteBucket(ctx, bucket.ID); err != nil {
		t.Fatalf("DeleteBucket returned error: %v", err)
	}
	handler, err := NewHandler(HandlerOptions{
		Store: store,
		Secrets: fakeSecretsManager{
			plaintext: []byte(`{"access_key_id":"access-key","secret_access_key":"secret-key"}`),
		},
		Factory: &fakeObjectClientFactory{client: &fakeObjectClient{}},
	})
	if err != nil {
		t.Fatalf("NewHandler returned error: %v", err)
	}

	_, err = handler.Handle(ctx, run)
	if !errors.Is(err, storage.ErrNotFound) {
		t.Fatalf("Handle error = %v, want %v", err, storage.ErrNotFound)
	}
}

type fakeObjectClient struct {
	headAttributes storage.ObjectAttributes
	headErrByKey   map[string]error
	headInputs     []s3compat.HeadObjectInput
	mu             sync.Mutex
}

func (c *fakeObjectClient) ListObjects(ctx context.Context, input s3compat.ListObjectsInput) (s3compat.ObjectPage, error) {
	return s3compat.ObjectPage{}, nil
}

func (c *fakeObjectClient) HeadObject(ctx context.Context, input s3compat.HeadObjectInput) (s3compat.HeadObjectData, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.headInputs = append(c.headInputs, input)
	if err := c.headErrByKey[input.Key]; err != nil {
		return s3compat.HeadObjectData{}, err
	}
	return s3compat.HeadObjectDataFromUpstreamAttributes(c.headAttributes), nil
}

func (c *fakeObjectClient) GetObject(context.Context, s3compat.HeadObjectInput) (io.ReadCloser, error) {
	return nil, errors.New("get object not implemented")
}

func (c *fakeObjectClient) GetObjectTagging(context.Context, s3compat.HeadObjectInput) (map[string]string, error) {
	return nil, nil
}

type fakeObjectClientFactory struct {
	client s3compat.ObjectClient
}

func (f *fakeObjectClientFactory) NewClient(ctx context.Context, config s3compat.BucketConfig, credentials s3compat.Credentials) (s3compat.ObjectClient, error) {
	return f.client, nil
}

type fakeSecretsManager struct {
	plaintext []byte
}

func (m fakeSecretsManager) Encrypt(ctx context.Context, plaintext []byte) (secrets.Envelope, error) {
	return secrets.Envelope{}, nil
}

func (m fakeSecretsManager) Decrypt(ctx context.Context, envelope secrets.Envelope) ([]byte, error) {
	return m.plaintext, nil
}

func testStore(t *testing.T, ctx context.Context) (*storage.Store, func()) {
	t.Helper()

	databaseURL := testdb.URL(t, ctx)
	migrationDir, err := filepath.Abs("../../../../../packages/storage/migrations")
	if err != nil {
		t.Fatalf("resolve migration dir: %v", err)
	}
	if err := testdb.MigrateIfNeeded(t, ctx, databaseURL, "buckets", func() error {
		return storage.RunMigrations(ctx, databaseURL, "file://"+migrationDir)
	}); err != nil {
		t.Fatal(testdb.MigrationTimeoutError(err))
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

func createTestBucket(t *testing.T, ctx context.Context, store *storage.Store) storage.Bucket {
	t.Helper()

	bucket, err := store.Buckets().CreateBucket(ctx, storage.CreateBucketParams{
		Name:        "import-test-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    storage.BucketUpstreamS3,
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  "import-test-data",
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
		_ = store.Buckets().DeleteBucket(context.Background(), bucket.ID)
	})

	return bucket
}

func createJobRun(t *testing.T, ctx context.Context, store *storage.Store, jobType storage.JobType, bucketID string, input storage.JobRunPayload) storage.JobRun {
	t.Helper()

	run, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       jobType,
		TargetType: "bucket",
		TargetID:   bucketID,
		Input:      input,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}

	return run
}
