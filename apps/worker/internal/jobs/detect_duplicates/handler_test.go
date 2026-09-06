package detect_duplicates

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/elei-io/pithosys/packages/db"
	"github.com/elei-io/pithosys/packages/secrets"
	"github.com/elei-io/pithosys/packages/storage"
	"github.com/elei-io/pithosys/packages/testdb"
	"github.com/elei-io/pithosys/packages/upstreams/s3compat"
)

var (
	migrateTestStoreOnce sync.Once
	migrateTestStoreErr  error
)

func TestHandlerCreatesDuplicateRelationsFromVerifiedGroup(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store)
	body := []byte("shared-bytes")
	bodyHash := sha256.Sum256(body)

	original, err := store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "older/original.jpg",
		Attributes: storage.ObjectAttributes{
			"upstream": map[string]any{
				"etag":          "\"shared\"",
				"size":          int64(len(body)),
				"last_modified": "2026-06-01T00:00:00Z",
			},
		},
	})
	if err != nil {
		t.Fatalf("UpsertObject original returned error: %v", err)
	}
	copyObject, err := store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "newer/copy.jpg",
		Attributes: storage.ObjectAttributes{
			"upstream": map[string]any{
				"etag":          "\"shared\"",
				"size":          int64(len(body)),
				"last_modified": "2026-06-02T00:00:00Z",
			},
		},
	})
	if err != nil {
		t.Fatalf("UpsertObject copy returned error: %v", err)
	}

	run, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type: storage.JobTypeDetectDuplicates,
		Input: storage.JobRunPayload{
			"scope": map[string]any{
				"bucket_ids": []any{bucket.ID},
			},
		},
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}

	client := &fakeObjectClient{
		objects: map[string]string{
			"older/original.jpg": string(body),
			"newer/copy.jpg":     string(body),
		},
	}
	handler, err := NewHandler(HandlerOptions{
		Store: store,
		Secrets: fakeSecretsManager{
			plaintext: []byte(`{"access_key_id":"access-key","secret_access_key":"secret-key"}`),
		},
		Factory:     &fakeObjectClientFactory{client: client},
		HashWorkers: 1,
	})
	if err != nil {
		t.Fatalf("NewHandler returned error: %v", err)
	}

	result, err := handler.Handle(ctx, run)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if result["verified_groups"] != 1 {
		t.Fatalf("verified_groups = %#v, want 1", result["verified_groups"])
	}
	if result["relations_created"] != 1 {
		t.Fatalf("relations_created = %#v, want 1", result["relations_created"])
	}

	relations, err := store.Relations().ListDuplicateRelationsBetween(ctx, storage.ListDuplicateRelationsBetweenParams{
		ObjectIDs: []string{original.ID, copyObject.ID},
	})
	if err != nil {
		t.Fatalf("ListDuplicateRelationsBetween returned error: %v", err)
	}
	if len(relations) != 1 {
		t.Fatalf("relations = %d, want 1", len(relations))
	}
	if relations[0].SourceObjectID != original.ID {
		t.Fatalf("source = %q, want %q", relations[0].SourceObjectID, original.ID)
	}
	if relations[0].TargetObjectID != copyObject.ID {
		t.Fatalf("target = %q, want %q", relations[0].TargetObjectID, copyObject.ID)
	}
	if relations[0].Attributes["content_sha256"] != hex.EncodeToString(bodyHash[:]) {
		t.Fatalf("relation hash = %#v", relations[0].Attributes["content_sha256"])
	}

	results, err := store.SearchPithosysQL(ctx, `
		FROM objects
		WHERE has_relation('duplicate', 'out')
	`, storage.SearchScope{BucketID: bucket.ID})
	if err != nil {
		t.Fatalf("SearchPithosysQL returned error: %v", err)
	}
	if len(results) != 1 || results[0].ID != original.ID {
		t.Fatalf("duplicate originals = %#v, want [%q]", results, original.ID)
	}
}

func TestHandlerRemovesRelationsWhenHashesDiffer(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store)
	first, err := store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "a.jpg",
		Attributes: storage.ObjectAttributes{
			"upstream": map[string]any{
				"etag":          "\"maybe-dup\"",
				"size":          int64(5),
				"last_modified": "2026-06-01T00:00:00Z",
			},
		},
	})
	if err != nil {
		t.Fatalf("UpsertObject first returned error: %v", err)
	}
	second, err := store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "b.jpg",
		Attributes: storage.ObjectAttributes{
			"upstream": map[string]any{
				"etag":          "\"maybe-dup\"",
				"size":          int64(5),
				"last_modified": "2026-06-02T00:00:00Z",
			},
		},
	})
	if err != nil {
		t.Fatalf("UpsertObject second returned error: %v", err)
	}
	if _, err := store.Relations().CreateRelation(ctx, storage.CreateRelationParams{
		SourceObjectID: first.ID,
		TargetObjectID: second.ID,
		RelationType:   storage.RelationTypeDuplicate,
	}); err != nil {
		t.Fatalf("CreateRelation returned error: %v", err)
	}

	run, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type: storage.JobTypeDetectDuplicates,
		Input: storage.JobRunPayload{
			"scope": map[string]any{
				"bucket_ids": []any{bucket.ID},
			},
		},
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}

	handler, err := NewHandler(HandlerOptions{
		Store: store,
		Secrets: fakeSecretsManager{
			plaintext: []byte(`{"access_key_id":"access-key","secret_access_key":"secret-key"}`),
		},
		Factory: &fakeObjectClientFactory{client: &fakeObjectClient{
			objects: map[string]string{
				"a.jpg": "alpha",
				"b.jpg": "beta!",
			},
		}},
		HashWorkers: 1,
	})
	if err != nil {
		t.Fatalf("NewHandler returned error: %v", err)
	}

	result, err := handler.Handle(ctx, run)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if result["verified_groups"] != 0 {
		t.Fatalf("verified_groups = %#v, want 0", result["verified_groups"])
	}
	if result["relations_removed"] != int64(1) {
		t.Fatalf("relations_removed = %#v, want 1", result["relations_removed"])
	}
}

type fakeObjectClient struct {
	objects map[string]string
}

func (c *fakeObjectClient) ListObjects(context.Context, s3compat.ListObjectsInput) (s3compat.ObjectPage, error) {
	return s3compat.ObjectPage{}, nil
}

func (c *fakeObjectClient) HeadObject(context.Context, s3compat.HeadObjectInput) (s3compat.HeadObjectData, error) {
	return s3compat.HeadObjectData{}, nil
}

func (c *fakeObjectClient) GetObject(_ context.Context, input s3compat.HeadObjectInput) (io.ReadCloser, error) {
	body, ok := c.objects[input.Key]
	if !ok {
		return nil, errors.New("object not found")
	}

	return io.NopCloser(strings.NewReader(body)), nil
}

func (c *fakeObjectClient) GetObjectTagging(context.Context, s3compat.HeadObjectInput) (map[string]string, error) {
	return nil, nil
}

type fakeObjectClientFactory struct {
	client s3compat.ObjectClient
}

func (f *fakeObjectClientFactory) NewClient(context.Context, s3compat.BucketConfig, s3compat.Credentials) (s3compat.ObjectClient, error) {
	return f.client, nil
}

type fakeSecretsManager struct {
	plaintext []byte
}

func (m fakeSecretsManager) Encrypt(context.Context, []byte) (secrets.Envelope, error) {
	return secrets.Envelope{}, nil
}

func (m fakeSecretsManager) Decrypt(context.Context, secrets.Envelope) ([]byte, error) {
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
		Name:        "detect-dup-test-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    storage.BucketUpstreamS3,
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  "detect-dup-data",
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
