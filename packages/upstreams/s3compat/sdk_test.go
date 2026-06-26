package s3compat

import (
	"reflect"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/s3/types"
	"github.com/ekkuleivonen/relic/packages/storage"
)

func TestObjectPageFromListObjectsV2Output(t *testing.T) {
	lastModified := mustTime(t, "2026-06-26T01:00:00Z")
	output := &s3.ListObjectsV2Output{
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
	}

	got := ObjectPageFromListObjectsV2Output(output)
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

	if !reflect.DeepEqual(got, want) {
		t.Fatalf("ObjectPageFromListObjectsV2Output mismatch\n got: %#v\nwant: %#v", got, want)
	}
}

func TestObjectPageFromListObjectsOutput(t *testing.T) {
	lastModified := mustTime(t, "2026-06-26T01:00:00Z")
	output := &s3.ListObjectsOutput{
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
	}

	got := ObjectPageFromListObjectsOutput(output)
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
		IsTruncated: true,
		NextMarker:  "photos/a.jpg",
	}

	if !reflect.DeepEqual(got, want) {
		t.Fatalf("ObjectPageFromListObjectsOutput mismatch\n got: %#v\nwant: %#v", got, want)
	}
}

func TestAttributesFromHeadObjectOutput(t *testing.T) {
	lastModified := mustTime(t, "2026-06-26T01:00:00Z")
	output := &s3.HeadObjectOutput{
		AcceptRanges:  aws.String("bytes"),
		CacheControl:  aws.String("max-age=3600"),
		ContentLength: aws.Int64(123),
		ContentType:   aws.String("image/jpeg"),
		ETag:          aws.String("\"abc123\""),
		LastModified:  aws.Time(lastModified),
		Metadata: map[string]string{
			"source": "camera",
		},
		StorageClass: types.StorageClassStandard,
		VersionId:    aws.String("version-1"),
	}
	want := storage.ObjectAttributes{
		"upstream": map[string]any{
			"etag":          "\"abc123\"",
			"size":          int64(123),
			"last_modified": "2026-06-26T01:00:00Z",
			"header": map[string]any{
				"accept_ranges": "bytes",
				"cache_control": "max-age=3600",
				"content_type":  "image/jpeg",
			},
			"metadata": map[string]any{
				"source": "camera",
			},
			"s3": map[string]any{
				"storage_class": "STANDARD",
				"version_id":    "version-1",
			},
		},
	}

	got := AttributesFromHeadObjectOutput(output)
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("AttributesFromHeadObjectOutput mismatch\n got: %#v\nwant: %#v", got, want)
	}
}

func TestAttributesFromHeadObjectOutputHandlesNil(t *testing.T) {
	got := AttributesFromHeadObjectOutput(nil)
	want := storage.ObjectAttributes{"upstream": map[string]any{}}

	if !reflect.DeepEqual(got, want) {
		t.Fatalf("AttributesFromHeadObjectOutput(nil) = %#v, want %#v", got, want)
	}
}
