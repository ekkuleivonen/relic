package import_objects

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/ekkuleivonen/relic/apps/worker/internal/jobs"
	"github.com/ekkuleivonen/relic/packages/db"
	"github.com/ekkuleivonen/relic/packages/secrets"
	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
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
		}},
	})
	if err != nil {
		t.Fatalf("PayloadFrom returned error: %v", err)
	}
	run := createJobRun(t, ctx, store, storage.JobTypeImportObjects, bucket.ID, input)
	client := &fakeObjectClient{
		headAttributes: storage.ObjectAttributes{
			"upstream": map[string]any{
				"etag": "\"abc123\"",
				"size": int64(123),
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
	if result["objects_imported"] != 1 {
		t.Fatalf("objects_imported = %#v, want 1", result["objects_imported"])
	}
	if len(client.headInputs) != 1 || client.headInputs[0].Key != "photos/a.jpg" {
		t.Fatalf("head inputs = %#v, want photos/a.jpg", client.headInputs)
	}

	objects, err := store.Objects().ListObjectsInScope(ctx, storage.ObjectScopeParams{BucketID: bucket.ID})
	if err != nil {
		t.Fatalf("ListObjectsInScope returned error: %v", err)
	}
	if len(objects) != 1 {
		t.Fatalf("object count = %d, want 1", len(objects))
	}
	if objects[0].AttributeProvenance["upstream"] != run.ID {
		t.Fatalf("provenance = %q, want %q", objects[0].AttributeProvenance["upstream"], run.ID)
	}
	upstream, ok := objects[0].Attributes["upstream"].(map[string]any)
	if !ok {
		t.Fatalf("upstream attributes = %#v, want object", objects[0].Attributes["upstream"])
	}
	if upstream["storage_class"] != "STANDARD" {
		t.Fatalf("storage_class = %#v, want STANDARD", upstream["storage_class"])
	}
	header, ok := upstream["header"].(map[string]any)
	if !ok || header["content_type"] != "image/jpeg" {
		t.Fatalf("header = %#v, want content_type image/jpeg", upstream["header"])
	}
}

type fakeObjectClient struct {
	headAttributes storage.ObjectAttributes
	headInputs     []s3compat.HeadObjectInput
}

func (c *fakeObjectClient) ListObjects(ctx context.Context, input s3compat.ListObjectsInput) (s3compat.ObjectPage, error) {
	return s3compat.ObjectPage{}, nil
}

func (c *fakeObjectClient) HeadObject(ctx context.Context, input s3compat.HeadObjectInput) (storage.ObjectAttributes, error) {
	c.headInputs = append(c.headInputs, input)
	return c.headAttributes, nil
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

	databaseURL := os.Getenv("DATABASE_URL")
	if databaseURL == "" {
		t.Skip("DATABASE_URL is not set")
	}

	migrationDir, err := filepath.Abs("../../../../../packages/storage/migrations")
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
