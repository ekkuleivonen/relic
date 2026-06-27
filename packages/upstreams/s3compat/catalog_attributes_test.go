package s3compat

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/smithy-go"
	"github.com/ekkuleivonen/relic/packages/search"
	"github.com/ekkuleivonen/relic/packages/storage"
)

func TestMergeTagAttributes(t *testing.T) {
	attributes := storage.ObjectAttributes{
		"upstream": map[string]any{
			"etag": "\"abc123\"",
		},
	}

	got := MergeTagAttributes(attributes, map[string]string{
		"environment": "prod",
		"team":        "data",
	})

	upstream := got["upstream"].(map[string]any)
	tag := upstream["tag"].(map[string]any)
	if tag["environment"] != "prod" {
		t.Fatalf("tag environment = %#v, want prod", tag["environment"])
	}
	if upstream["etag"] != "\"abc123\"" {
		t.Fatalf("etag = %#v, want preserved", upstream["etag"])
	}
}

func TestFetchCatalogAttributesMergesTags(t *testing.T) {
	lastModified := mustTime(t, "2026-06-26T01:00:00Z")
	client := &catalogAttributesFakeClient{
		head: HeadObjectData{
			Output: headObjectOutputWithRequired(lastModified),
		},
		tags: map[string]string{"environment": "prod"},
	}

	got, err := FetchCatalogAttributes(context.Background(), client, HeadObjectInput{
		Bucket: "example-bucket",
		Key:    "photos/a.jpg",
	}, platformCaptureFieldsForTests())
	if err != nil {
		t.Fatalf("FetchCatalogAttributes() error = %v", err)
	}

	upstream := got["upstream"].(map[string]any)
	tag := upstream["tag"].(map[string]any)
	if tag["environment"] != "prod" {
		t.Fatalf("tag environment = %#v, want prod", tag["environment"])
	}
}

func TestFetchCatalogAttributesSkipsTaggingWhenDisabled(t *testing.T) {
	lastModified := mustTime(t, "2026-06-26T01:00:00Z")
	client := &catalogAttributesFakeClient{
		head: HeadObjectData{
			Output: headObjectOutputWithRequired(lastModified),
		},
		tags: map[string]string{"environment": "prod"},
	}

	got, err := FetchCatalogAttributes(context.Background(), client, HeadObjectInput{
		Bucket: "example-bucket",
		Key:    "photos/a.jpg",
	}, requiredCaptureFields())
	if err != nil {
		t.Fatalf("FetchCatalogAttributes() error = %v", err)
	}

	if client.taggingCalls != 0 {
		t.Fatalf("GetObjectTagging calls = %d, want 0", client.taggingCalls)
	}
	upstream := got["upstream"].(map[string]any)
	if _, ok := upstream["tag"]; ok {
		t.Fatal("tag attributes present, want none when tagging disabled")
	}
}

func TestFetchCatalogAttributesIgnoresUnsupportedTagging(t *testing.T) {
	lastModified := mustTime(t, "2026-06-26T01:00:00Z")
	client := &catalogAttributesFakeClient{
		head: HeadObjectData{
			Output: headObjectOutputWithRequired(lastModified),
		},
		taggingErr: &unsupportedTaggingError{code: "NotImplemented"},
	}

	got, err := FetchCatalogAttributes(context.Background(), client, HeadObjectInput{
		Bucket: "example-bucket",
		Key:    "photos/a.jpg",
	}, platformCaptureFieldsForTests())
	if err != nil {
		t.Fatalf("FetchCatalogAttributes() error = %v", err)
	}

	upstream := got["upstream"].(map[string]any)
	if _, ok := upstream["tag"]; ok {
		t.Fatal("tag attributes present, want none when tagging unsupported")
	}
}

func platformCaptureFieldsForTests() []storage.UpstreamCaptureField {
	fields := requiredCaptureFields()
	fields = append(fields, platformField(
		"upstream.tagging_all",
		"upstream.tag",
		storage.CaptureExtractorTaggingAll,
		"*",
		storage.CaptureFieldCategoryOptional,
		search.TypeString,
		storage.CaptureSourceTagging,
	))

	return fields
}

type catalogAttributesFakeClient struct {
	head         HeadObjectData
	tags         map[string]string
	taggingErr   error
	taggingCalls int
}

func (c *catalogAttributesFakeClient) ListObjects(context.Context, ListObjectsInput) (ObjectPage, error) {
	return ObjectPage{}, nil
}

func (c *catalogAttributesFakeClient) HeadObject(context.Context, HeadObjectInput) (HeadObjectData, error) {
	return c.head, nil
}

func (c *catalogAttributesFakeClient) GetObjectTagging(context.Context, HeadObjectInput) (map[string]string, error) {
	c.taggingCalls++
	if c.taggingErr != nil {
		return nil, c.taggingErr
	}

	return c.tags, nil
}

func TestIsGetObjectTaggingUnsupported(t *testing.T) {
	err := &unsupportedTaggingError{code: "NotImplemented"}
	if !IsGetObjectTaggingUnsupported(err) {
		t.Fatal("IsGetObjectTaggingUnsupported() = false, want true")
	}
	if IsGetObjectTaggingUnsupported(errors.New("boom")) {
		t.Fatal("IsGetObjectTaggingUnsupported() = true, want false for generic error")
	}
}

type unsupportedTaggingError struct {
	code string
}

func (e *unsupportedTaggingError) Error() string {
	return e.code
}

func (e *unsupportedTaggingError) ErrorCode() string {
	return e.code
}

func (e *unsupportedTaggingError) ErrorMessage() string {
	return e.code
}

func (e *unsupportedTaggingError) ErrorFault() smithy.ErrorFault {
	return smithy.FaultUnknown
}

func headObjectOutputWithRequired(lastModified time.Time) *s3.HeadObjectOutput {
	return &s3.HeadObjectOutput{
		ContentLength: aws.Int64(123),
		ETag:          aws.String("\"abc123\""),
		LastModified:  aws.Time(lastModified),
	}
}
