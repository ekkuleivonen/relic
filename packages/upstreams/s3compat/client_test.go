package s3compat

import (
	"context"
	"errors"
	"reflect"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/s3/types"
)

func TestSDKClientListObjectsUsesListObjectsV2ByDefault(t *testing.T) {
	lastModified := mustTime(t, "2026-06-26T01:00:00Z")
	api := &fakeS3API{
		listObjectsV2Output: &s3.ListObjectsV2Output{
			Contents: []types.Object{
				{
					Key:          aws.String("photos/a.jpg"),
					ETag:         aws.String("\"abc123\""),
					Size:         aws.Int64(123),
					LastModified: aws.Time(lastModified),
					StorageClass: types.ObjectStorageClassStandard,
				},
			},
			IsTruncated:           aws.Bool(true),
			NextContinuationToken: aws.String("next-token"),
		},
	}
	client, err := NewSDKClient(SDKClientOptions{API: api})
	if err != nil {
		t.Fatalf("NewSDKClient returned error: %v", err)
	}

	page, err := client.ListObjects(context.Background(), ListObjectsInput{
		Bucket:            "example-bucket",
		Prefix:            "photos/",
		ContinuationToken: "token",
	})
	if err != nil {
		t.Fatalf("ListObjects returned error: %v", err)
	}

	if api.listObjectsV2Input == nil {
		t.Fatal("ListObjectsV2 was not called")
	}
	if aws.ToString(api.listObjectsV2Input.Bucket) != "example-bucket" {
		t.Fatalf("Bucket = %q, want example-bucket", aws.ToString(api.listObjectsV2Input.Bucket))
	}
	if aws.ToString(api.listObjectsV2Input.Prefix) != "photos/" {
		t.Fatalf("Prefix = %q, want photos/", aws.ToString(api.listObjectsV2Input.Prefix))
	}
	if aws.ToString(api.listObjectsV2Input.ContinuationToken) != "token" {
		t.Fatalf("ContinuationToken = %q, want token", aws.ToString(api.listObjectsV2Input.ContinuationToken))
	}

	want := ObjectPage{
		Objects: []ListedObject{
			{
				Key:          "photos/a.jpg",
				ETag:         "\"abc123\"",
				Size:         123,
				LastModified: lastModified,
				StorageClass: "STANDARD",
			},
		},
		IsTruncated:           true,
		NextContinuationToken: "next-token",
	}
	if !reflect.DeepEqual(page, want) {
		t.Fatalf("page mismatch\n got: %#v\nwant: %#v", page, want)
	}
}

func TestSDKClientListObjectsUsesLegacyListWhenConfigured(t *testing.T) {
	lastModified := mustTime(t, "2026-06-26T01:00:00Z")
	api := &fakeS3API{
		listObjectsOutput: &s3.ListObjectsOutput{
			Contents: []types.Object{
				{
					Key:          aws.String("photos/a.jpg"),
					ETag:         aws.String("\"abc123\""),
					Size:         aws.Int64(123),
					LastModified: aws.Time(lastModified),
					StorageClass: types.ObjectStorageClassStandard,
				},
			},
			IsTruncated: aws.Bool(true),
			NextMarker:  aws.String("photos/a.jpg"),
		},
	}
	client, err := NewSDKClient(SDKClientOptions{
		API:           api,
		UseLegacyList: true,
	})
	if err != nil {
		t.Fatalf("NewSDKClient returned error: %v", err)
	}

	page, err := client.ListObjects(context.Background(), ListObjectsInput{
		Bucket: "example-bucket",
		Prefix: "photos/",
		Marker: "marker",
	})
	if err != nil {
		t.Fatalf("ListObjects returned error: %v", err)
	}

	if api.listObjectsInput == nil {
		t.Fatal("ListObjects was not called")
	}
	if aws.ToString(api.listObjectsInput.Bucket) != "example-bucket" {
		t.Fatalf("Bucket = %q, want example-bucket", aws.ToString(api.listObjectsInput.Bucket))
	}
	if aws.ToString(api.listObjectsInput.Prefix) != "photos/" {
		t.Fatalf("Prefix = %q, want photos/", aws.ToString(api.listObjectsInput.Prefix))
	}
	if aws.ToString(api.listObjectsInput.Marker) != "marker" {
		t.Fatalf("Marker = %q, want marker", aws.ToString(api.listObjectsInput.Marker))
	}
	if page.NextMarker != "photos/a.jpg" {
		t.Fatalf("NextMarker = %q, want photos/a.jpg", page.NextMarker)
	}
}

func TestSDKClientHeadObject(t *testing.T) {
	lastModified := mustTime(t, "2026-06-26T01:00:00Z")
	api := &fakeS3API{
		headObjectOutput: &s3.HeadObjectOutput{
			ContentLength: aws.Int64(123),
			ContentType:   aws.String("image/jpeg"),
			ETag:          aws.String("\"abc123\""),
			LastModified:  aws.Time(lastModified),
			StorageClass:  types.StorageClassStandard,
			VersionId:     aws.String("version-1"),
		},
	}
	client, err := NewSDKClient(SDKClientOptions{API: api})
	if err != nil {
		t.Fatalf("NewSDKClient returned error: %v", err)
	}

	head, err := client.HeadObject(context.Background(), HeadObjectInput{
		Bucket:    "example-bucket",
		Key:       "photos/a.jpg",
		VersionID: "version-1",
	})
	if err != nil {
		t.Fatalf("HeadObject returned error: %v", err)
	}

	if api.headObjectInput == nil {
		t.Fatal("HeadObject was not called")
	}
	if aws.ToString(api.headObjectInput.Bucket) != "example-bucket" {
		t.Fatalf("Bucket = %q, want example-bucket", aws.ToString(api.headObjectInput.Bucket))
	}
	if aws.ToString(api.headObjectInput.Key) != "photos/a.jpg" {
		t.Fatalf("Key = %q, want photos/a.jpg", aws.ToString(api.headObjectInput.Key))
	}
	if aws.ToString(api.headObjectInput.VersionId) != "version-1" {
		t.Fatalf("VersionId = %q, want version-1", aws.ToString(api.headObjectInput.VersionId))
	}

	if head.Output == nil || aws.ToString(head.Output.ETag) != "\"abc123\"" {
		t.Fatalf("head output etag = %#v, want abc123", head.Output)
	}
}

func TestSDKClientGetObjectTagging(t *testing.T) {
	api := &fakeS3API{
		getObjectTaggingOutput: &s3.GetObjectTaggingOutput{
			TagSet: []types.Tag{
				{Key: aws.String("environment"), Value: aws.String("prod")},
			},
		},
	}
	client, err := NewSDKClient(SDKClientOptions{API: api})
	if err != nil {
		t.Fatalf("NewSDKClient returned error: %v", err)
	}

	tags, err := client.GetObjectTagging(context.Background(), HeadObjectInput{
		Bucket:    "example-bucket",
		Key:       "photos/a.jpg",
		VersionID: "version-1",
	})
	if err != nil {
		t.Fatalf("GetObjectTagging returned error: %v", err)
	}
	if tags["environment"] != "prod" {
		t.Fatalf("tags = %#v, want environment=prod", tags)
	}
	if aws.ToString(api.getObjectTaggingInput.Bucket) != "example-bucket" {
		t.Fatalf("Bucket = %q, want example-bucket", aws.ToString(api.getObjectTaggingInput.Bucket))
	}
}

func TestNewSDKClientRejectsNilAPI(t *testing.T) {
	_, err := NewSDKClient(SDKClientOptions{})
	if err == nil {
		t.Fatal("NewSDKClient returned nil error, want nil API error")
	}
}

func TestSDKClientReturnsAPIErrors(t *testing.T) {
	api := &fakeS3API{listObjectsV2Err: errors.New("list failed")}
	client, err := NewSDKClient(SDKClientOptions{API: api})
	if err != nil {
		t.Fatalf("NewSDKClient returned error: %v", err)
	}

	_, err = client.ListObjects(context.Background(), ListObjectsInput{Bucket: "example-bucket"})
	if err == nil {
		t.Fatal("ListObjects returned nil error, want API error")
	}
}

type fakeS3API struct {
	listObjectsV2Input  *s3.ListObjectsV2Input
	listObjectsV2Output *s3.ListObjectsV2Output
	listObjectsV2Err    error

	listObjectsInput  *s3.ListObjectsInput
	listObjectsOutput *s3.ListObjectsOutput
	listObjectsErr    error

	headObjectInput  *s3.HeadObjectInput
	headObjectOutput *s3.HeadObjectOutput
	headObjectErr    error

	getObjectInput  *s3.GetObjectInput
	getObjectOutput *s3.GetObjectOutput
	getObjectErr    error

	getObjectTaggingInput  *s3.GetObjectTaggingInput
	getObjectTaggingOutput *s3.GetObjectTaggingOutput
	getObjectTaggingErr    error
}

func (api *fakeS3API) ListObjectsV2(ctx context.Context, input *s3.ListObjectsV2Input, options ...func(*s3.Options)) (*s3.ListObjectsV2Output, error) {
	api.listObjectsV2Input = input
	return api.listObjectsV2Output, api.listObjectsV2Err
}

func (api *fakeS3API) ListObjects(ctx context.Context, input *s3.ListObjectsInput, options ...func(*s3.Options)) (*s3.ListObjectsOutput, error) {
	api.listObjectsInput = input
	return api.listObjectsOutput, api.listObjectsErr
}

func (api *fakeS3API) HeadObject(ctx context.Context, input *s3.HeadObjectInput, options ...func(*s3.Options)) (*s3.HeadObjectOutput, error) {
	api.headObjectInput = input
	return api.headObjectOutput, api.headObjectErr
}

func (api *fakeS3API) GetObject(ctx context.Context, input *s3.GetObjectInput, options ...func(*s3.Options)) (*s3.GetObjectOutput, error) {
	api.getObjectInput = input
	return api.getObjectOutput, api.getObjectErr
}

func (api *fakeS3API) GetObjectTagging(ctx context.Context, input *s3.GetObjectTaggingInput, options ...func(*s3.Options)) (*s3.GetObjectTaggingOutput, error) {
	api.getObjectTaggingInput = input
	return api.getObjectTaggingOutput, api.getObjectTaggingErr
}
