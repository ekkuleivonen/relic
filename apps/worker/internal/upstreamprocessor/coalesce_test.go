package upstreamprocessor

import (
	"testing"

	"github.com/ekkuleivonen/relic/packages/storage"
)

func TestCoalesceMutationsKeepsLatestIntentForSameKey(t *testing.T) {
	mutations := CoalesceMutations([]CoalesceInput{
		{EventID: "evt_1", BucketID: "bucket_a", Key: "photos/a.jpg", JobType: storage.JobTypeImportObjects},
		{EventID: "evt_2", BucketID: "bucket_a", Key: "photos/a.jpg", JobType: storage.JobTypeRemoveObjects},
	})

	if len(mutations) != 1 {
		t.Fatalf("mutation count = %d, want 1", len(mutations))
	}
	if mutations[0].JobType != storage.JobTypeRemoveObjects {
		t.Fatalf("job type = %q, want remove_objects", mutations[0].JobType)
	}
	if len(mutations[0].EventIDs) != 2 {
		t.Fatalf("event id count = %d, want 2", len(mutations[0].EventIDs))
	}
}

func TestCoalesceMutationsDistinctKeys(t *testing.T) {
	mutations := CoalesceMutations([]CoalesceInput{
		{EventID: "evt_1", BucketID: "bucket_a", Key: "photos/a.jpg", JobType: storage.JobTypeImportObjects},
		{EventID: "evt_2", BucketID: "bucket_a", Key: "photos/b.jpg", JobType: storage.JobTypeImportObjects},
	})

	if len(mutations) != 2 {
		t.Fatalf("mutation count = %d, want 2", len(mutations))
	}
}

func TestCoalesceMutationsPreservesObjectIDForRemove(t *testing.T) {
	mutations := CoalesceMutations([]CoalesceInput{
		{
			EventID:  "evt_1",
			BucketID: "bucket_a",
			Key:      "photos/a.jpg",
			JobType:  storage.JobTypeRemoveObjects,
			ObjectID: "object_123",
		},
	})

	if mutations[0].ObjectID != "object_123" {
		t.Fatalf("object id = %q, want object_123", mutations[0].ObjectID)
	}
}

func TestGroupMutationsByJob(t *testing.T) {
	groups := GroupMutationsByJob(CoalesceMutations([]CoalesceInput{
		{EventID: "evt_1", BucketID: "bucket_a", Key: "a.jpg", JobType: storage.JobTypeImportObjects},
		{EventID: "evt_2", BucketID: "bucket_a", Key: "b.jpg", JobType: storage.JobTypeImportObjects},
		{EventID: "evt_3", BucketID: "bucket_a", Key: "c.jpg", JobType: storage.JobTypeRemoveObjects, ObjectID: "object_c"},
	}))

	if len(groups) != 2 {
		t.Fatalf("group count = %d, want 2", len(groups))
	}
}
