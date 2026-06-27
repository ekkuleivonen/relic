package s3compat

import (
	"context"
	"io"
	"strings"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

func TestHashObject(t *testing.T) {
	client := &hashObjectFakeClient{
		body: "hello duplicate world",
	}

	hash, bytesRead, err := HashObject(context.Background(), client, "bucket", HeadObjectInput{Key: "a.txt"})
	if err != nil {
		t.Fatalf("HashObject returned error: %v", err)
	}
	if hash != "a97d012cbfe626f2023dfbe6f33e4f26bd4a9755276f7ae6536ec14b39172c63" {
		t.Fatalf("hash = %q, want known sha256 of test body", hash)
	}
	if bytesRead != int64(len("hello duplicate world")) {
		t.Fatalf("bytesRead = %d, want %d", bytesRead, len("hello duplicate world"))
	}
}

type hashObjectFakeClient struct {
	body string
}

func (c *hashObjectFakeClient) ListObjects(context.Context, ListObjectsInput) (ObjectPage, error) {
	return ObjectPage{}, nil
}

func (c *hashObjectFakeClient) HeadObject(context.Context, HeadObjectInput) (HeadObjectData, error) {
	return HeadObjectData{}, nil
}

func (c *hashObjectFakeClient) GetObject(context.Context, HeadObjectInput) (io.ReadCloser, error) {
	return io.NopCloser(strings.NewReader(c.body)), nil
}

func (c *hashObjectFakeClient) GetObjectTagging(context.Context, HeadObjectInput) (map[string]string, error) {
	return nil, nil
}

func TestSDKClientGetObject(t *testing.T) {
	api := &fakeS3API{
		getObjectOutput: &s3.GetObjectOutput{
			Body: io.NopCloser(strings.NewReader("payload")),
		},
	}
	client, err := NewSDKClient(SDKClientOptions{API: api})
	if err != nil {
		t.Fatalf("NewSDKClient returned error: %v", err)
	}

	body, err := client.GetObject(context.Background(), HeadObjectInput{
		Bucket: "bucket",
		Key:    "key.txt",
	})
	if err != nil {
		t.Fatalf("GetObject returned error: %v", err)
	}
	defer body.Close()

	if api.getObjectInput == nil {
		t.Fatal("expected GetObject API call")
	}
	if aws.ToString(api.getObjectInput.Bucket) != "bucket" {
		t.Fatalf("bucket = %q, want bucket", aws.ToString(api.getObjectInput.Bucket))
	}
	if aws.ToString(api.getObjectInput.Key) != "key.txt" {
		t.Fatalf("key = %q, want key.txt", aws.ToString(api.getObjectInput.Key))
	}
}
