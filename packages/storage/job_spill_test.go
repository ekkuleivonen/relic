package storage

import (
	"context"
	"testing"
	"time"

	"github.com/ekkuleivonen/relic/packages/secrets"
)

func TestJobSpillStoreInsertAndQuery(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	run, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
		Type:       JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   "bucket_spill_test",
		Input:      JobRunPayload{"bucket_id": "bucket_spill_test"},
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}

	if err := store.JobSpill().InsertKeys(ctx, run.ID, []string{"photos/a.jpg", "photos/b.jpg"}); err != nil {
		t.Fatalf("InsertKeys returned error: %v", err)
	}
	if err := store.JobSpill().InsertKeys(ctx, run.ID, []string{"photos/a.jpg"}); err != nil {
		t.Fatalf("InsertKeys duplicate returned error: %v", err)
	}

	count, err := store.JobSpill().CountKeys(ctx, run.ID)
	if err != nil {
		t.Fatalf("CountKeys returned error: %v", err)
	}
	if count != 2 {
		t.Fatalf("count = %d, want 2", count)
	}

	pending, err := store.JobSpill().FilterKeysNotInSpill(ctx, run.ID, []string{
		"photos/a.jpg",
		"photos/b.jpg",
		"photos/c.jpg",
	})
	if err != nil {
		t.Fatalf("FilterKeysNotInSpill returned error: %v", err)
	}
	if len(pending) != 1 || pending[0] != "photos/c.jpg" {
		t.Fatalf("pending = %#v, want [photos/c.jpg]", pending)
	}

	bucket, err := store.Buckets().CreateBucket(ctx, CreateBucketParams{
		Name:        "job-spill-test-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    BucketUpstreamS3,
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  "job-spill-test-data",
		Prefix:      "photos/",
		EncryptedCredentials: secrets.Envelope{
			KeyID:      "local-dev",
			Algorithm:  secrets.AlgorithmXChaCha20Poly1305,
			Nonce:      []byte("012345678901234567890"),
			Ciphertext: []byte("ciphertext"),
		},
	})
	if err != nil {
		t.Fatalf("CreateBucket returned error: %v", err)
	}

	seenAt := run.CreatedAt
	stale, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "photos/stale.jpg",
		SeenAt:   &seenAt,
	})
	if err != nil {
		t.Fatalf("UpsertObject stale returned error: %v", err)
	}
	if _, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "photos/a.jpg",
		SeenAt:   &seenAt,
	}); err != nil {
		t.Fatalf("UpsertObject current returned error: %v", err)
	}

	missing := []Object{}
	if err := store.JobSpill().StreamObjectsInScopeMissingFromSpill(ctx, run.ID, ObjectScopeParams{
		BucketID: bucket.ID,
		Prefix:   "photos/",
	}, func(object Object) error {
		missing = append(missing, object)
		return nil
	}); err != nil {
		t.Fatalf("StreamObjectsInScopeMissingFromSpill returned error: %v", err)
	}
	if len(missing) != 1 || missing[0].ID != stale.ID {
		t.Fatalf("missing = %#v, want stale object %q", missing, stale.ID)
	}

	if err := store.JobSpill().DeleteForJobRun(ctx, run.ID); err != nil {
		t.Fatalf("DeleteForJobRun returned error: %v", err)
	}
	count, err = store.JobSpill().CountKeys(ctx, run.ID)
	if err != nil {
		t.Fatalf("CountKeys after delete returned error: %v", err)
	}
	if count != 0 {
		t.Fatalf("count after delete = %d, want 0", count)
	}
}
