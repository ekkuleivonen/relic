package storage

import "testing"

func TestResolveBucketForEventMatchesAWSRegion(t *testing.T) {
	buckets := []Bucket{
		{
			ID:          "bucket_east",
			BucketName:  "shared-data",
			EndpointURL: "https://s3.amazonaws.com",
			Region:      "us-east-1",
		},
		{
			ID:          "bucket_west",
			BucketName:  "shared-data",
			EndpointURL: "https://s3.us-west-2.amazonaws.com",
			Region:      "us-west-2",
		},
	}

	bucket, reason := ResolveBucketForEvent(buckets, BucketEventMatch{
		Origin:             "aws:us-west-2",
		UpstreamBucketName: "shared-data",
		ObjectKey:          "photos/a.jpg",
	})
	if reason != "" {
		t.Fatalf("skip reason = %q, want empty", reason)
	}
	if bucket.ID != "bucket_west" {
		t.Fatalf("bucket ID = %q, want bucket_west", bucket.ID)
	}
}

func TestResolveBucketForEventMatchesEndpointOrigin(t *testing.T) {
	buckets := []Bucket{
		{
			ID:          "bucket_a",
			BucketName:  "data",
			EndpointURL: "https://minio-a.example.test:9000",
		},
		{
			ID:          "bucket_b",
			BucketName:  "data",
			EndpointURL: "https://minio-b.example.test:9000",
		},
	}

	bucket, reason := ResolveBucketForEvent(buckets, BucketEventMatch{
		Origin:             "endpoint:minio-b.example.test:9000",
		UpstreamBucketName: "data",
		ObjectKey:          "photos/a.jpg",
	})
	if reason != "" {
		t.Fatalf("skip reason = %q, want empty", reason)
	}
	if bucket.ID != "bucket_b" {
		t.Fatalf("bucket ID = %q, want bucket_b", bucket.ID)
	}
}

func TestResolveBucketForEventUsesPrefixWhenOriginWeak(t *testing.T) {
	buckets := []Bucket{
		{
			ID:          "bucket_raw",
			BucketName:  "data",
			EndpointURL: "https://minio.example.test:9000",
			Prefix:      "raw/",
		},
		{
			ID:          "bucket_archive",
			BucketName:  "data",
			EndpointURL: "https://minio.example.test:9000",
			Prefix:      "archive/",
		},
	}

	bucket, reason := ResolveBucketForEvent(buckets, BucketEventMatch{
		Origin:             "eventsource:minio:s3",
		UpstreamBucketName: "data",
		ObjectKey:          "raw/photos/a.jpg",
	})
	if reason != "" {
		t.Fatalf("skip reason = %q, want empty", reason)
	}
	if bucket.ID != "bucket_raw" {
		t.Fatalf("bucket ID = %q, want bucket_raw", bucket.ID)
	}
}

func TestResolveBucketForEventAmbiguousWithoutPrefix(t *testing.T) {
	buckets := []Bucket{
		{
			ID:          "bucket_a",
			BucketName:  "data",
			EndpointURL: "https://minio-a.example.test:9000",
		},
		{
			ID:          "bucket_b",
			BucketName:  "data",
			EndpointURL: "https://minio-b.example.test:9000",
		},
	}

	_, reason := ResolveBucketForEvent(buckets, BucketEventMatch{
		Origin:             "eventsource:minio:s3",
		UpstreamBucketName: "data",
		ObjectKey:          "photos/a.jpg",
	})
	if reason != "ambiguous_bucket" {
		t.Fatalf("skip reason = %q, want ambiguous_bucket", reason)
	}
}

func TestResolveBucketForEventMatchesRustFSDeploymentOrigin(t *testing.T) {
	buckets := []Bucket{
		{
			ID:          "bucket_rustfs",
			BucketName:  "relic-test-01",
			EndpointURL: "http://192.168.30.216:9000",
		},
	}

	bucket, reason := ResolveBucketForEvent(buckets, BucketEventMatch{
		Origin:             "deployment:2369dcb4-348b-4d30-8fc9-61ab089ba4bc",
		UpstreamBucketName: "relic-test-01",
		ObjectKey:          "photos/a.jpg",
	})
	if reason != "" {
		t.Fatalf("skip reason = %q, want empty", reason)
	}
	if bucket.ID != "bucket_rustfs" {
		t.Fatalf("bucket ID = %q, want bucket_rustfs", bucket.ID)
	}
}
