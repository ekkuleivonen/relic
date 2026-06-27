package refresh_objects

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

func TestHandlerRefreshesObjectsFromHead(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store)
	existing, err := store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "photos/a.jpg",
		Attributes: storage.ObjectAttributes{
			"upstream": map[string]any{"etag": "\"old\""},
		},
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}
	input, err := jobs.PayloadFrom(jobs.ObjectMutationInput{
		BucketID: bucket.ID,
		Objects: []jobs.ObjectEvidence{{
			ID:           existing.ID,
			Key:          existing.Key,
			StorageClass: "STANDARD",
		}},
	})
	if err != nil {
		t.Fatalf("PayloadFrom returned error: %v", err)
	}
	run := createJobRun(t, ctx, store, storage.JobTypeRefreshObjects, bucket.ID, input)
	client := &fakeObjectClient{
		headAttributes: storage.ObjectAttributes{
			"upstream": map[string]any{
				"etag": "\"new\"",
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
	if result["objects_refreshed"] != 1 {
		t.Fatalf("objects_refreshed = %#v, want 1", result["objects_refreshed"])
	}

	refreshed, err := store.Objects().GetObject(ctx, existing.ID)
	if err != nil {
		t.Fatalf("GetObject returned error: %v", err)
	}
	if refreshed.ID != existing.ID {
		t.Fatalf("refreshed ID = %q, want %q", refreshed.ID, existing.ID)
	}
	if refreshed.AttributeProvenance["upstream"] != run.ID {
		t.Fatalf("provenance = %q, want %q", refreshed.AttributeProvenance["upstream"], run.ID)
	}
	upstream, ok := refreshed.Attributes["upstream"].(map[string]any)
	if !ok {
		t.Fatalf("upstream attributes = %#v, want object", refreshed.Attributes["upstream"])
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
	if progressed.Progress["objects_headed"] != float64(1) {
		t.Fatalf("progress objects_headed = %#v, want 1", progressed.Progress["objects_headed"])
	}
	if progressed.Progress["objects_upserted"] != float64(1) {
		t.Fatalf("progress objects_upserted = %#v, want 1", progressed.Progress["objects_upserted"])
	}
}

type fakeObjectClient struct {
	headAttributes storage.ObjectAttributes
}

func (c *fakeObjectClient) ListObjects(ctx context.Context, input s3compat.ListObjectsInput) (s3compat.ObjectPage, error) {
	return s3compat.ObjectPage{}, nil
}

func (c *fakeObjectClient) HeadObject(ctx context.Context, input s3compat.HeadObjectInput) (s3compat.HeadObjectData, error) {
	return s3compat.HeadObjectDataFromUpstreamAttributes(c.headAttributes), nil
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

func createTestBucket(t *testing.T, ctx context.Context, store *storage.Store) storage.Bucket {
	t.Helper()

	bucket, err := store.Buckets().CreateBucket(ctx, storage.CreateBucketParams{
		Name:        "refresh-test-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    storage.BucketUpstreamS3,
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  "refresh-test-data",
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
