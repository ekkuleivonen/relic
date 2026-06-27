package storage

import (
	"context"
	"testing"
	"time"
)

func TestRelationStoreCreateAndListDuplicateRelations(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	source, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "source.jpg",
	})
	if err != nil {
		t.Fatalf("UpsertObject source returned error: %v", err)
	}
	target, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "target.jpg",
	})
	if err != nil {
		t.Fatalf("UpsertObject target returned error: %v", err)
	}

	relations := store.Relations()
	created, err := relations.CreateRelation(ctx, CreateRelationParams{
		SourceObjectID: source.ID,
		TargetObjectID: target.ID,
		RelationType:   RelationTypeDuplicate,
		Attributes: RelationAttributes{
			"content_sha256": "abc123",
		},
		CreatedByType:  "job",
		CreatedByRunID: "jobrun_test",
	})
	if err != nil {
		t.Fatalf("CreateRelation returned error: %v", err)
	}
	if created.SourceObjectID != source.ID || created.TargetObjectID != target.ID {
		t.Fatalf("created relation = %#v", created)
	}

	listed, err := relations.ListDuplicateRelationsBetween(ctx, ListDuplicateRelationsBetweenParams{
		ObjectIDs: []string{source.ID, target.ID},
	})
	if err != nil {
		t.Fatalf("ListDuplicateRelationsBetween returned error: %v", err)
	}
	if len(listed) != 1 {
		t.Fatalf("listed relations = %d, want 1", len(listed))
	}

	updated, err := relations.CreateRelation(ctx, CreateRelationParams{
		SourceObjectID: source.ID,
		TargetObjectID: target.ID,
		RelationType:   RelationTypeDuplicate,
		Attributes: RelationAttributes{
			"content_sha256": "def456",
		},
		CreatedByRunID: "jobrun_test_2",
	})
	if err != nil {
		t.Fatalf("CreateRelation upsert returned error: %v", err)
	}
	if updated.Attributes["content_sha256"] != "def456" {
		t.Fatalf("updated attributes = %#v", updated.Attributes)
	}
}

func TestRelationStoreListRelationTypes(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	source, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "source.jpg",
	})
	if err != nil {
		t.Fatalf("UpsertObject source returned error: %v", err)
	}
	target, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "target.jpg",
	})
	if err != nil {
		t.Fatalf("UpsertObject target returned error: %v", err)
	}
	if _, err := store.Relations().CreateRelation(ctx, CreateRelationParams{
		SourceObjectID: source.ID,
		TargetObjectID: target.ID,
		RelationType:   RelationTypeDuplicate,
	}); err != nil {
		t.Fatalf("CreateRelation returned error: %v", err)
	}

	types, err := store.Relations().ListRelationTypes(ctx)
	if err != nil {
		t.Fatalf("ListRelationTypes returned error: %v", err)
	}
	if len(types) != 1 || types[0] != RelationTypeDuplicate {
		t.Fatalf("types = %#v, want [%q]", types, RelationTypeDuplicate)
	}
}

func TestFindDuplicateCandidateGroups(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	upsertDuplicateCandidate := func(key, etag string, size int64) {
		t.Helper()
		_, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
			BucketID: bucket.ID,
			Key:      key,
			Attributes: ObjectAttributes{
				"upstream": map[string]any{
					"etag":          etag,
					"size":          size,
					"last_modified": time.Now().UTC().Format(time.RFC3339),
				},
			},
		})
		if err != nil {
			t.Fatalf("UpsertObject %q returned error: %v", key, err)
		}
	}

	upsertDuplicateCandidate("a.jpg", "\"dup\"", 100)
	upsertDuplicateCandidate("b.jpg", "\"dup\"", 100)
	upsertDuplicateCandidate("solo.jpg", "\"solo\"", 50)

	groups, err := store.Objects().FindDuplicateCandidateGroups(ctx, DuplicateDetectScope{
		BucketIDs: []string{bucket.ID},
	})
	if err != nil {
		t.Fatalf("FindDuplicateCandidateGroups returned error: %v", err)
	}
	if len(groups) != 1 {
		t.Fatalf("groups = %d, want 1", len(groups))
	}
	if len(groups[0].Objects) != 2 {
		t.Fatalf("group objects = %d, want 2", len(groups[0].Objects))
	}
	if groups[0].ETag != "\"dup\"" || groups[0].Size != 100 {
		t.Fatalf("group = %#v, want dup/100", groups[0])
	}
}
