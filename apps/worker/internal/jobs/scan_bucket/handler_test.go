package scan_bucket

import (
	"context"
	"fmt"
	"path/filepath"
	"sync"
	"testing"
	"time"

	syncbucket "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/sync_bucket"
	"github.com/ekkuleivonen/relic/packages/db"
	"github.com/ekkuleivonen/relic/packages/secrets"
	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/testdb"
	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
	"github.com/ekkuleivonen/relic/packages/verification"
)

const testModulus uint32 = 8

var (
	migrateTestStoreOnce sync.Once
	migrateTestStoreErr  error
)

func TestHandlerReportsHealthyWhenFingerprintsMatch(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "")
	partition := verification.PartitionFromIndex(3, testModulus)
	key := keyForPartitionIndex(t, partition.Index, testModulus)
	listedAt := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)

	upsertLocalObject(t, ctx, store, bucket.ID, key, 100, listedAt)
	run := createScanRun(t, ctx, store, bucket.ID)
	client := &fakeObjectClient{
		page: s3compat.ObjectPage{
			Objects: []s3compat.ListedObject{
				listedObject(key, "\"abc\"", 100, listedAt),
			},
		},
	}
	handler := newTestHandler(t, store, client)

	result, err := handler.Handle(ctx, run)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if result["status"] != "healthy" {
		t.Fatalf("status = %#v, want healthy", result["status"])
	}
	if result["listing_pass_complete"] != true {
		t.Fatalf("listing_pass_complete = %#v, want true", result["listing_pass_complete"])
	}

	assertChildJobCount(t, ctx, store, run.ID, storage.JobTypeSyncBucket, 0)
	assertChildJobCount(t, ctx, store, run.ID, storage.JobTypeImportObjects, 0)
	assertChildJobCount(t, ctx, store, run.ID, storage.JobTypeRefreshObjects, 0)
	assertChildJobCount(t, ctx, store, run.ID, storage.JobTypeRemoveObjects, 0)
}

func TestHandlerReportsNeedsSyncOnCountDrift(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "")
	partition := verification.PartitionFromIndex(3, testModulus)
	keyA := keyForPartitionIndex(t, partition.Index, testModulus)
	keyB := secondKeyForPartitionIndex(t, keyA, partition.Index, testModulus)
	listedAt := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)

	upsertLocalObject(t, ctx, store, bucket.ID, keyA, 100, listedAt)
	run := createScanRun(t, ctx, store, bucket.ID)
	client := &fakeObjectClient{
		page: s3compat.ObjectPage{
			Objects: []s3compat.ListedObject{
				listedObject(keyA, "\"a\"", 100, listedAt),
				listedObject(keyB, "\"b\"", 200, listedAt),
			},
		},
	}
	handler := newTestHandler(t, store, client)

	result, err := handler.Handle(ctx, run)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if result["status"] != "needs_sync" {
		t.Fatalf("status = %#v, want needs_sync", result["status"])
	}

	mismatched := stringSliceField(result["partitions_mismatched"])
	if len(mismatched) != 1 || mismatched[0] != partition.ID() {
		t.Fatalf("partitions_mismatched = %#v, want [%q]", mismatched, partition.ID())
	}

	syncChild := assertSingleSyncChild(t, ctx, store, run.ID)
	assertPartitionSyncInput(t, syncChild, bucket.ID, "", partition, run.ID)
}

func TestHandlerReportsNeedsSyncOnBytesDrift(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "")
	partition := verification.PartitionFromIndex(5, testModulus)
	key := keyForPartitionIndex(t, partition.Index, testModulus)
	listedAt := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)

	upsertLocalObject(t, ctx, store, bucket.ID, key, 100, listedAt)
	run := createScanRun(t, ctx, store, bucket.ID)
	client := &fakeObjectClient{
		page: s3compat.ObjectPage{
			Objects: []s3compat.ListedObject{
				listedObject(key, "\"abc\"", 999, listedAt),
			},
		},
	}
	handler := newTestHandler(t, store, client)

	result, err := handler.Handle(ctx, run)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if result["status"] != "needs_sync" {
		t.Fatalf("status = %#v, want needs_sync", result["status"])
	}
}

func TestHandlerDetectsNewUpstreamKeyNotInCatalog(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "")
	partition := verification.PartitionFromIndex(2, testModulus)
	key := keyForPartitionIndex(t, partition.Index, testModulus)
	listedAt := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)
	run := createScanRun(t, ctx, store, bucket.ID)
	client := &fakeObjectClient{
		page: s3compat.ObjectPage{
			Objects: []s3compat.ListedObject{
				listedObject(key, "\"new\"", 50, listedAt),
			},
		},
	}
	handler := newTestHandler(t, store, client)

	result, err := handler.Handle(ctx, run)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if result["status"] != "needs_sync" {
		t.Fatalf("status = %#v, want needs_sync", result["status"])
	}
}

func TestHandlerDetectsRemovedUpstreamKey(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "")
	partition := verification.PartitionFromIndex(1, testModulus)
	key := keyForPartitionIndex(t, partition.Index, testModulus)
	listedAt := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)

	upsertLocalObject(t, ctx, store, bucket.ID, key, 100, listedAt)
	run := createScanRun(t, ctx, store, bucket.ID)
	client := &fakeObjectClient{page: s3compat.ObjectPage{}}
	handler := newTestHandler(t, store, client)

	result, err := handler.Handle(ctx, run)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if result["status"] != "needs_sync" {
		t.Fatalf("status = %#v, want needs_sync", result["status"])
	}
}

func TestHandlerNeverEnqueuesMutationJobsDirectly(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "")
	partition := verification.PartitionFromIndex(4, testModulus)
	key := keyForPartitionIndex(t, partition.Index, testModulus)
	listedAt := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)
	run := createScanRun(t, ctx, store, bucket.ID)
	client := &fakeObjectClient{
		page: s3compat.ObjectPage{
			Objects: []s3compat.ListedObject{
				listedObject(key, "\"only-upstream\"", 10, listedAt),
			},
		},
	}
	handler := newTestHandler(t, store, client)

	if _, err := handler.Handle(ctx, run); err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}

	assertChildJobCount(t, ctx, store, run.ID, storage.JobTypeImportObjects, 0)
	assertChildJobCount(t, ctx, store, run.ID, storage.JobTypeRefreshObjects, 0)
	assertChildJobCount(t, ctx, store, run.ID, storage.JobTypeRemoveObjects, 0)
	assertChildJobCount(t, ctx, store, run.ID, storage.JobTypeSyncBucket, 1)
}

func TestHandlerUsesSingleUpstreamListingPass(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "")
	partition := verification.PartitionFromIndex(6, testModulus)
	key := keyForPartitionIndex(t, partition.Index, testModulus)
	listedAt := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)

	upsertLocalObject(t, ctx, store, bucket.ID, key, 100, listedAt)
	run := createScanRun(t, ctx, store, bucket.ID)
	client := &fakeObjectClient{
		page: s3compat.ObjectPage{
			Objects: []s3compat.ListedObject{
				listedObject(key, "\"abc\"", 100, listedAt),
			},
		},
	}
	handler := newTestHandler(t, store, client)

	if _, err := handler.Handle(ctx, run); err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if len(client.listInputs) != 1 {
		t.Fatalf("list calls = %d, want 1", len(client.listInputs))
	}
}

func TestHandlerListsEffectiveScopePrefix(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "raw/")
	run := createScanRunWithInput(t, ctx, store, bucket.ID, storage.JobRunPayload{
		"bucket_id": bucket.ID,
		"prefix":    "batch/",
	})
	client := &fakeObjectClient{page: s3compat.ObjectPage{}}
	handler := newTestHandler(t, store, client)

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

func TestHandlerDoesNotReportHealthyWhenBudgetExhausted(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "")
	partition := verification.PartitionFromIndex(0, testModulus)
	key := keyForPartitionIndex(t, partition.Index, testModulus)
	listedAt := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)

	upsertLocalObject(t, ctx, store, bucket.ID, key, 100, listedAt)
	run := createScanRun(t, ctx, store, bucket.ID)
	client := &fakeObjectClient{
		pages: []s3compat.ObjectPage{
			{
				Objects: []s3compat.ListedObject{
					listedObject(key, "\"abc\"", 100, listedAt),
					listedObject("objects/extra.dat", "\"extra\"", 50, listedAt),
				},
				IsTruncated:           true,
				NextContinuationToken: "token-1",
			},
			{
				Objects: []s3compat.ListedObject{
					listedObject("objects/more.dat", "\"more\"", 50, listedAt),
				},
			},
		},
	}
	handler := newTestHandlerWithOptions(t, store, client, HandlerOptions{
		Store:   store,
		Secrets: testSecretsManager(),
		Factory: &fakeObjectClientFactory{client: client},
		Now:     func() time.Time { return time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC) },
		Modulus: testModulus,
		Budget:  ScanBudgetConfig{MaxObjectsListed: 1},
	})

	result, err := handler.Handle(ctx, run)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if result["listing_pass_complete"] != false {
		t.Fatalf("listing_pass_complete = %#v, want false", result["listing_pass_complete"])
	}
	if result["status"] == "healthy" {
		t.Fatalf("status = healthy, want not healthy when listing incomplete")
	}
}

func TestHandlerDoesNotFetchNextPageWhenDeadlineReached(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	start := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)
	afterDeadline := start.Add(2 * time.Minute)

	bucket := createTestBucket(t, ctx, store, "")
	run := createScanRun(t, ctx, store, bucket.ID)
	client := &fakeObjectClient{
		pages: []s3compat.ObjectPage{
			{
				Objects: []s3compat.ListedObject{
					listedObject("objects/a.dat", "\"a\"", 100, start),
				},
				IsTruncated:           true,
				NextContinuationToken: "token-1",
			},
			{
				Objects: []s3compat.ListedObject{
					listedObject("objects/b.dat", "\"b\"", 100, start),
				},
			},
		},
	}

	callCount := 0
	handler := newTestHandlerWithOptions(t, store, client, HandlerOptions{
		Store:   store,
		Secrets: testSecretsManager(),
		Factory: &fakeObjectClientFactory{client: client},
		Now: func() time.Time {
			callCount++
			if callCount > 1 {
				return afterDeadline
			}
			return start
		},
		Modulus: testModulus,
		Budget:  ScanBudgetConfig{MaxDuration: time.Minute},
	})

	result, err := handler.Handle(ctx, run)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if len(client.listInputs) != 1 {
		t.Fatalf("list calls = %d, want 1", len(client.listInputs))
	}
	if result["listing_pass_complete"] != false {
		t.Fatalf("listing_pass_complete = %#v, want false", result["listing_pass_complete"])
	}
}

func TestHandlerFailsWhenListObjectsFails(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "")
	run := createScanRun(t, ctx, store, bucket.ID)
	client := &fakeObjectClient{err: fmt.Errorf("upstream unavailable")}
	handler := newTestHandler(t, store, client)

	if _, err := handler.Handle(ctx, run); err == nil {
		t.Fatal("Handle returned nil error, want list error")
	}
	assertChildJobCount(t, ctx, store, run.ID, storage.JobTypeSyncBucket, 0)
}

func TestHandlerFailsWithInvalidCredentials(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "")
	run := createScanRun(t, ctx, store, bucket.ID)
	client := &fakeObjectClient{}
	handler, err := NewHandler(HandlerOptions{
		Store:   store,
		Secrets: fakeSecretsManager{plaintext: []byte(`{"access_key_id":""}`)},
		Factory: &fakeObjectClientFactory{client: client},
		Modulus: testModulus,
		Now:     func() time.Time { return time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC) },
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
}

func TestHandlerEscalationSyncReconcilesPartition(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "")
	partition := verification.PartitionFromIndex(7, testModulus)
	keyIn := keyForPartitionIndex(t, partition.Index, testModulus)
	keyStale := secondKeyForPartitionIndex(t, keyIn, partition.Index, testModulus)
	listedAt := time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC)

	upsertLocalObject(t, ctx, store, bucket.ID, keyStale, 50, listedAt)
	run := createScanRun(t, ctx, store, bucket.ID)
	client := &fakeObjectClient{
		page: s3compat.ObjectPage{
			Objects: []s3compat.ListedObject{
				listedObject(keyIn, "\"in\"", 100, listedAt),
			},
		},
	}
	scanHandler := newTestHandler(t, store, client)
	if _, err := scanHandler.Handle(ctx, run); err != nil {
		t.Fatalf("scan Handle returned error: %v", err)
	}

	syncChild := assertSingleSyncChild(t, ctx, store, run.ID)
	assertPartitionSyncInput(t, syncChild, bucket.ID, "", partition, run.ID)
	syncHandler, err := syncbucket.NewHandler(syncbucket.HandlerOptions{
		Store:   store,
		Secrets: testSecretsManager(),
		Factory: &fakeObjectClientFactory{client: client},
	})
	if err != nil {
		t.Fatalf("sync NewHandler returned error: %v", err)
	}

	result, err := syncHandler.Handle(ctx, syncChild)
	if err != nil {
		t.Fatalf("sync Handle returned error: %v", err)
	}
	if result["import_objects_count"] != 1 {
		t.Fatalf("import count = %#v, want 1", result["import_objects_count"])
	}
	if result["remove_objects_count"] != 1 {
		t.Fatalf("remove count = %#v, want 1", result["remove_objects_count"])
	}
}

type fakeObjectClient struct {
	page        s3compat.ObjectPage
	pages       []s3compat.ObjectPage
	err         error
	listInputs  []s3compat.ListObjectsInput
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

func (c *fakeObjectClient) ListObjects(ctx context.Context, input s3compat.ListObjectsInput) (s3compat.ObjectPage, error) {
	c.listInputs = append(c.listInputs, input)
	index := len(c.listInputs) - 1
	if c.err != nil {
		return s3compat.ObjectPage{}, c.err
	}
	if len(c.pages) > 0 {
		if index >= len(c.pages) {
			return s3compat.ObjectPage{}, fmt.Errorf("unexpected list page %d", index)
		}
		return c.pages[index], nil
	}
	return c.page, nil
}

func (c *fakeObjectClient) HeadObject(context.Context, s3compat.HeadObjectInput) (storage.ObjectAttributes, error) {
	return storage.ObjectAttributes{"upstream": map[string]any{}}, nil
}

func newTestHandler(t *testing.T, store *storage.Store, client *fakeObjectClient) *Handler {
	t.Helper()

	return newTestHandlerWithOptions(t, store, client, HandlerOptions{
		Store:   store,
		Secrets: testSecretsManager(),
		Factory: &fakeObjectClientFactory{client: client},
		Now:     func() time.Time { return time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC) },
		Modulus: testModulus,
	})
}

func newTestHandlerWithOptions(t *testing.T, store *storage.Store, client *fakeObjectClient, options HandlerOptions) *Handler {
	t.Helper()

	handler, err := NewHandler(options)
	if err != nil {
		t.Fatalf("NewHandler returned error: %v", err)
	}

	return handler
}

func testSecretsManager() fakeSecretsManager {
	return fakeSecretsManager{
		plaintext: []byte(`{"access_key_id":"access-key","secret_access_key":"secret-key"}`),
	}
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

	return store, pool.Close
}

func createTestBucket(t *testing.T, ctx context.Context, store *storage.Store, prefix string) storage.Bucket {
	t.Helper()

	bucket, err := store.Buckets().CreateBucket(ctx, storage.CreateBucketParams{
		Name:        "scan-test-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    storage.BucketUpstreamS3,
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  "scan-test-data",
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

func createScanRun(t *testing.T, ctx context.Context, store *storage.Store, bucketID string) storage.JobRun {
	t.Helper()

	return createScanRunWithInput(t, ctx, store, bucketID, storage.JobRunPayload{
		"bucket_id": bucketID,
	})
}

func createScanRunWithInput(t *testing.T, ctx context.Context, store *storage.Store, bucketID string, input storage.JobRunPayload) storage.JobRun {
	t.Helper()

	if input == nil {
		input = storage.JobRunPayload{}
	}
	if _, ok := input["bucket_id"]; !ok {
		input["bucket_id"] = bucketID
	}

	run, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       storage.JobTypeScanBucket,
		TargetType: "bucket",
		TargetID:   bucketID,
		Input:      input,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}

	return run
}

func upsertLocalObject(t *testing.T, ctx context.Context, store *storage.Store, bucketID, key string, size int64, modified time.Time) {
	t.Helper()

	_, err := store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
		BucketID: bucketID,
		Key:      key,
		Attributes: storage.ObjectAttributes{
			"upstream": map[string]any{
				"etag":          fmt.Sprintf("\"%s\"", key),
				"size":          size,
				"last_modified": modified.Format(time.RFC3339),
				"storage_class": "STANDARD",
			},
		},
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}
}

func listedObject(key, etag string, size int64, modified time.Time) s3compat.ListedObject {
	return s3compat.ListedObject{
		Key:          key,
		ETag:         etag,
		Size:         size,
		LastModified: modified,
		StorageClass: "STANDARD",
	}
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

func secondKeyForPartitionIndex(t *testing.T, firstKey string, index, modulus uint32) string {
	t.Helper()

	for i := range 10_000 {
		key := fmt.Sprintf("objects/alt-%d.dat", i)
		if key == firstKey {
			continue
		}
		if verification.PartitionIndex(key, modulus) == index {
			return key
		}
	}

	t.Fatalf("could not find second key for partition %d/%d", index, modulus)
	return ""
}

func assertChildJobCount(t *testing.T, ctx context.Context, store *storage.Store, parentRunID string, jobType storage.JobType, want int) {
	t.Helper()

	children, err := store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		Type:            jobType,
		RequestedByType: "job",
		RequestedByID:   parentRunID,
		Limit:           100,
	})
	if err != nil {
		t.Fatalf("ListJobRuns returned error: %v", err)
	}
	if len(children) != want {
		t.Fatalf("%s child count = %d, want %d", jobType, len(children), want)
	}
}

func assertSingleSyncChild(t *testing.T, ctx context.Context, store *storage.Store, parentRunID string) storage.JobRun {
	t.Helper()

	children, err := store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		Type:            storage.JobTypeSyncBucket,
		RequestedByType: "job",
		RequestedByID:   parentRunID,
		Limit:           10,
	})
	if err != nil {
		t.Fatalf("ListJobRuns returned error: %v", err)
	}
	if len(children) != 1 {
		t.Fatalf("sync child count = %d, want 1", len(children))
	}

	return children[0]
}

func assertPartitionSyncInput(t *testing.T, run storage.JobRun, bucketID, scopePrefix string, partition verification.Partition, sourceRunID string) {
	t.Helper()

	input, err := syncbucket.ParseSyncBucketInput(run)
	if err != nil {
		t.Fatalf("ParseSyncBucketInput returned error: %v", err)
	}
	if input.BucketID != bucketID {
		t.Fatalf("BucketID = %q, want %q", input.BucketID, bucketID)
	}
	if input.ScopePrefix != scopePrefix {
		t.Fatalf("ScopePrefix = %q, want %q", input.ScopePrefix, scopePrefix)
	}
	if input.Partition == nil {
		t.Fatal("Partition = nil, want hash partition")
	}
	if input.Partition.Index != partition.Index || input.Partition.Modulus != partition.Modulus {
		t.Fatalf("Partition = %#v, want index=%d modulus=%d", input.Partition, partition.Index, partition.Modulus)
	}
	if input.SourceJobRunID != sourceRunID {
		t.Fatalf("SourceJobRunID = %q, want %q", input.SourceJobRunID, sourceRunID)
	}
}

func stringSliceField(value any) []string {
	raw, ok := value.([]any)
	if !ok {
		return nil
	}

	out := make([]string, 0, len(raw))
	for _, item := range raw {
		if typed, ok := item.(string); ok {
			out = append(out, typed)
		}
	}

	return out
}
