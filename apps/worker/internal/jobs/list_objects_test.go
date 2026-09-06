package jobs

import (
	"context"
	"fmt"
	"io"
	"testing"
	"time"

	"github.com/elei-io/pithosys/packages/upstreams/s3compat"
)

type fakeListBudget struct {
	allow func(count int) bool
}

func (b *fakeListBudget) Allow(count int) bool {
	if b.allow == nil {
		return true
	}
	return b.allow(count)
}

func (b *fakeListBudget) Record(count int) {}

func (b *fakeListBudget) ObjectsListed() int64 { return 0 }

type recordingListClient struct {
	pages      []s3compat.ObjectPage
	listInputs []s3compat.ListObjectsInput
	err        error
}

func (c *recordingListClient) ListObjects(_ context.Context, input s3compat.ListObjectsInput) (s3compat.ObjectPage, error) {
	c.listInputs = append(c.listInputs, input)
	index := len(c.listInputs) - 1
	if c.err != nil {
		return s3compat.ObjectPage{}, c.err
	}
	if index >= len(c.pages) {
		return s3compat.ObjectPage{}, fmt.Errorf("unexpected list page %d", index)
	}
	return c.pages[index], nil
}

func (c *recordingListClient) HeadObject(context.Context, s3compat.HeadObjectInput) (s3compat.HeadObjectData, error) {
	return s3compat.HeadObjectData{}, fmt.Errorf("not implemented")
}

func (c *recordingListClient) GetObject(context.Context, s3compat.HeadObjectInput) (io.ReadCloser, error) {
	return nil, fmt.Errorf("not implemented")
}

func (c *recordingListClient) GetObjectTagging(context.Context, s3compat.HeadObjectInput) (map[string]string, error) {
	return nil, fmt.Errorf("not implemented")
}

func TestListAllObjectsReturnsAllPages(t *testing.T) {
	client := &recordingListClient{
		pages: []s3compat.ObjectPage{
			{
				Objects: []s3compat.ListedObject{
					{Key: "a.txt", Size: 1, LastModified: time.Unix(0, 0).UTC()},
				},
				IsTruncated:           true,
				NextContinuationToken: "token-1",
			},
			{
				Objects: []s3compat.ListedObject{
					{Key: "b.txt", Size: 2, LastModified: time.Unix(0, 0).UTC()},
				},
			},
		},
	}

	var keys []string
	complete, listed, err := ListAllObjects(context.Background(), ListAllObjectsOptions{
		Client:      client,
		BucketName:  "bucket",
		Prefix:      "raw/",
		BucketLabel: "bucket",
		OnObject: func(object s3compat.ListedObject) error {
			keys = append(keys, object.Key)
			return nil
		},
	})
	if err != nil {
		t.Fatalf("ListAllObjects returned error: %v", err)
	}
	if !complete {
		t.Fatal("complete = false, want true")
	}
	if listed != 2 {
		t.Fatalf("listed = %d, want 2", listed)
	}
	if len(keys) != 2 || keys[0] != "a.txt" || keys[1] != "b.txt" {
		t.Fatalf("keys = %#v, want [a.txt b.txt]", keys)
	}
	if len(client.listInputs) != 2 {
		t.Fatalf("list calls = %d, want 2", len(client.listInputs))
	}
	if client.listInputs[1].ContinuationToken != "token-1" {
		t.Fatalf("second continuation token = %q, want token-1", client.listInputs[1].ContinuationToken)
	}
}

func TestListAllObjectsStopsWhenBudgetExhausted(t *testing.T) {
	client := &recordingListClient{
		pages: []s3compat.ObjectPage{
			{
				Objects: []s3compat.ListedObject{
					{Key: "a.txt", Size: 1, LastModified: time.Unix(0, 0).UTC()},
					{Key: "b.txt", Size: 2, LastModified: time.Unix(0, 0).UTC()},
				},
				IsTruncated:           true,
				NextContinuationToken: "token-1",
			},
			{
				Objects: []s3compat.ListedObject{
					{Key: "c.txt", Size: 3, LastModified: time.Unix(0, 0).UTC()},
				},
			},
		},
	}
	budget := &countingListBudget{max: 1}

	complete, listed, err := ListAllObjects(context.Background(), ListAllObjectsOptions{
		Client:      client,
		BucketName:  "bucket",
		BucketLabel: "bucket",
		Budget:      budget,
		OnObject:    func(s3compat.ListedObject) error { return nil },
	})
	if err != nil {
		t.Fatalf("ListAllObjects returned error: %v", err)
	}
	if complete {
		t.Fatal("complete = true, want false when budget exhausted")
	}
	if listed != 1 {
		t.Fatalf("listed = %d, want 1", listed)
	}
	if len(client.listInputs) != 1 {
		t.Fatalf("list calls = %d, want 1", len(client.listInputs))
	}
}

func TestListAllObjectsStopsPaginationWhenBudgetExpired(t *testing.T) {
	client := &recordingListClient{
		pages: []s3compat.ObjectPage{
			{
				Objects: []s3compat.ListedObject{
					{Key: "a.txt", Size: 1, LastModified: time.Unix(0, 0).UTC()},
				},
				IsTruncated:           true,
				NextContinuationToken: "token-1",
			},
			{
				Objects: []s3compat.ListedObject{
					{Key: "b.txt", Size: 2, LastModified: time.Unix(0, 0).UTC()},
				},
			},
		},
	}
	budget := &countingListBudget{
		allowZero: false,
	}

	complete, _, err := ListAllObjects(context.Background(), ListAllObjectsOptions{
		Client:      client,
		BucketName:  "bucket",
		BucketLabel: "bucket",
		Budget:      budget,
		OnObject:    func(s3compat.ListedObject) error { return nil },
	})
	if err != nil {
		t.Fatalf("ListAllObjects returned error: %v", err)
	}
	if complete {
		t.Fatal("complete = true, want false when budget expired before next page")
	}
	if len(client.listInputs) != 1 {
		t.Fatalf("list calls = %d, want 1", len(client.listInputs))
	}
}

func TestListAllObjectsAppliesFilter(t *testing.T) {
	client := &recordingListClient{
		pages: []s3compat.ObjectPage{
			{
				Objects: []s3compat.ListedObject{
					{Key: "keep.txt", Size: 1, LastModified: time.Unix(0, 0).UTC()},
					{Key: "skip.txt", Size: 2, LastModified: time.Unix(0, 0).UTC()},
				},
			},
		},
	}

	var keys []string
	_, listed, err := ListAllObjects(context.Background(), ListAllObjectsOptions{
		Client:      client,
		BucketName:  "bucket",
		BucketLabel: "bucket",
		Filter: func(object s3compat.ListedObject) bool {
			return object.Key == "keep.txt"
		},
		OnObject: func(object s3compat.ListedObject) error {
			keys = append(keys, object.Key)
			return nil
		},
	})
	if err != nil {
		t.Fatalf("ListAllObjects returned error: %v", err)
	}
	if listed != 1 {
		t.Fatalf("listed = %d, want 1", listed)
	}
	if keys[0] != "keep.txt" {
		t.Fatalf("keys = %#v, want [keep.txt]", keys)
	}
}

func TestListAllObjectsResumesFromCheckpoint(t *testing.T) {
	client := &recordingListClient{
		pages: []s3compat.ObjectPage{
			{
				Objects: []s3compat.ListedObject{
					{Key: "b.txt", Size: 2, LastModified: time.Unix(0, 0).UTC()},
				},
			},
		},
	}

	var keys []string
	complete, listed, err := ListAllObjects(context.Background(), ListAllObjectsOptions{
		Client:      client,
		BucketName:  "bucket",
		BucketLabel: "bucket",
		Start: ListCheckpoint{
			ContinuationToken: "token-1",
			ObjectsListed:     1,
		},
		OnObject: func(object s3compat.ListedObject) error {
			keys = append(keys, object.Key)
			return nil
		},
	})
	if err != nil {
		t.Fatalf("ListAllObjects returned error: %v", err)
	}
	if !complete {
		t.Fatal("complete = false, want true")
	}
	if listed != 2 {
		t.Fatalf("listed = %d, want 2", listed)
	}
	if len(client.listInputs) != 1 {
		t.Fatalf("list calls = %d, want 1", len(client.listInputs))
	}
	if client.listInputs[0].ContinuationToken != "token-1" {
		t.Fatalf("continuation token = %q, want token-1", client.listInputs[0].ContinuationToken)
	}
	if len(keys) != 1 || keys[0] != "b.txt" {
		t.Fatalf("keys = %#v, want [b.txt]", keys)
	}
}

type countingListBudget struct {
	max       int64
	count     int64
	allowZero bool
}

func (b *countingListBudget) Allow(count int) bool {
	if count <= 0 {
		return b.allowZero
	}
	if b.count+int64(count) > b.max {
		return false
	}
	return true
}

func (b *countingListBudget) Record(count int) {
	if count > 0 {
		b.count += int64(count)
	}
}

func (b *countingListBudget) ObjectsListed() int64 {
	return b.count
}
