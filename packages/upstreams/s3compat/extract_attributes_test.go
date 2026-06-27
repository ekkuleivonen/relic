package s3compat

import (
	"net/http"
	"reflect"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/s3/types"
	"github.com/ekkuleivonen/relic/packages/search"
	"github.com/ekkuleivonen/relic/packages/storage"
)

func TestExtractAttributesRequiredFields(t *testing.T) {
	lastModified := mustTime(t, "2026-06-26T01:00:00Z")
	head := HeadObjectData{
		Output: &s3.HeadObjectOutput{
			ContentLength: aws.Int64(123),
			ContentType:   aws.String("image/jpeg"),
			ETag:          aws.String("\"abc123\""),
			LastModified:  aws.Time(lastModified),
			StorageClass:  types.StorageClassStandard,
			VersionId:     aws.String("version-1"),
		},
	}

	fields := []storage.UpstreamCaptureField{
		platformField("upstream.head.etag", "upstream.etag", storage.CaptureExtractorSDKField, "ETag", storage.CaptureFieldCategoryRequired, search.TypeString),
		platformField("upstream.head.size", "upstream.size", storage.CaptureExtractorSDKField, "ContentLength", storage.CaptureFieldCategoryRequired, search.TypeInteger),
		platformField("upstream.head.last_modified", "upstream.last_modified", storage.CaptureExtractorSDKField, "LastModified", storage.CaptureFieldCategoryRequired, search.TypeTimestamp),
	}

	got, err := ExtractAttributes(fields, head, nil)
	if err != nil {
		t.Fatalf("ExtractAttributes() error = %v", err)
	}

	want := storage.ObjectAttributes{
		"upstream": map[string]any{
			"etag":          "\"abc123\"",
			"size":          int64(123),
			"last_modified": "2026-06-26T01:00:00Z",
		},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("ExtractAttributes mismatch\n got: %#v\nwant: %#v", got, want)
	}
}

func TestExtractAttributesOmitsDisabledOptionalField(t *testing.T) {
	lastModified := mustTime(t, "2026-06-26T01:00:00Z")
	head := HeadObjectData{
		Output: &s3.HeadObjectOutput{
			ContentLength: aws.Int64(123),
			ContentType:   aws.String("image/jpeg"),
			ETag:          aws.String("\"abc123\""),
			LastModified:  aws.Time(lastModified),
		},
	}

	fields := []storage.UpstreamCaptureField{
		platformField("upstream.head.etag", "upstream.etag", storage.CaptureExtractorSDKField, "ETag", storage.CaptureFieldCategoryRequired, search.TypeString),
		platformField("upstream.head.size", "upstream.size", storage.CaptureExtractorSDKField, "ContentLength", storage.CaptureFieldCategoryRequired, search.TypeInteger),
		platformField("upstream.head.last_modified", "upstream.last_modified", storage.CaptureExtractorSDKField, "LastModified", storage.CaptureFieldCategoryRequired, search.TypeTimestamp),
		{
			ID: "upstream.head.header.content_type", AttributePath: "upstream.header.content_type", Enabled: false,
			Category: storage.CaptureFieldCategoryOptional, Origin: storage.CaptureFieldOriginPlatform,
			CaptureSource: storage.CaptureSourceHead, ExtractorType: storage.CaptureExtractorSDKField, ExtractorRef: "ContentType", ValueType: search.TypeString,
		},
	}

	got, err := ExtractAttributes(fields, head, nil)
	if err != nil {
		t.Fatalf("ExtractAttributes() error = %v", err)
	}

	upstream := got["upstream"].(map[string]any)
	if _, ok := upstream["header"]; ok {
		t.Fatal("header attributes present, want omitted disabled field")
	}
}

func TestExtractAttributesMetadataAllAndTaggingAll(t *testing.T) {
	head := HeadObjectData{
		Output: &s3.HeadObjectOutput{
			ContentLength: aws.Int64(123),
			ETag:          aws.String("\"abc123\""),
			LastModified:  aws.Time(mustTime(t, "2026-06-26T01:00:00Z")),
			Metadata: map[string]string{
				"source": "camera",
			},
		},
	}

	fields := requiredCaptureFields()
	fields = append(fields,
		platformField("upstream.head.metadata_all", "upstream.metadata", storage.CaptureExtractorMetadataAll, "*", storage.CaptureFieldCategoryOptional, search.TypeString),
		platformField("upstream.tagging_all", "upstream.tag", storage.CaptureExtractorTaggingAll, "*", storage.CaptureFieldCategoryOptional, search.TypeString, storage.CaptureSourceTagging),
	)

	got, err := ExtractAttributes(fields, head, map[string]string{"environment": "prod"})
	if err != nil {
		t.Fatalf("ExtractAttributes() error = %v", err)
	}

	upstream := got["upstream"].(map[string]any)
	metadata := upstream["metadata"].(map[string]any)
	if metadata["source"] != "camera" {
		t.Fatalf("metadata source = %#v, want camera", metadata["source"])
	}
	tag := upstream["tag"].(map[string]any)
	if tag["environment"] != "prod" {
		t.Fatalf("tag environment = %#v, want prod", tag["environment"])
	}
}

func TestExtractAttributesUserCustomExtractors(t *testing.T) {
	head := HeadObjectData{
		Output: &s3.HeadObjectOutput{
			ContentLength: aws.Int64(123),
			ETag:          aws.String("\"abc123\""),
			LastModified:  aws.Time(mustTime(t, "2026-06-26T01:00:00Z")),
			Metadata: map[string]string{
				"cost-center": "eng",
			},
		},
		ResponseHeaders: http.Header{
			"X-Acme-Deployment-Id": []string{"deploy-42"},
		},
	}

	fields := requiredCaptureFields()
	fields = append(fields,
		userField("upstream.vendor.deployment_id", storage.CaptureExtractorResponseHeader, "x-acme-deployment-id", search.TypeString),
		userField("upstream.metadata.cost_center", storage.CaptureExtractorMetadataKey, "cost-center", search.TypeString),
		userField("upstream.tag.environment", storage.CaptureExtractorTagKey, "environment", search.TypeString, storage.CaptureSourceTagging),
	)

	got, err := ExtractAttributes(fields, head, map[string]string{"environment": "prod"})
	if err != nil {
		t.Fatalf("ExtractAttributes() error = %v", err)
	}

	upstream := got["upstream"].(map[string]any)
	if upstream["vendor"].(map[string]any)["deployment_id"] != "deploy-42" {
		t.Fatalf("vendor deployment_id = %#v, want deploy-42", upstream["vendor"])
	}
	if upstream["metadata"].(map[string]any)["cost_center"] != "eng" {
		t.Fatalf("metadata cost_center = %#v, want eng", upstream["metadata"])
	}
	if upstream["tag"].(map[string]any)["environment"] != "prod" {
		t.Fatalf("tag environment = %#v, want prod", upstream["tag"])
	}
}

func platformField(id, path string, extractor storage.CaptureExtractorType, ref string, category storage.CaptureFieldCategory, valueType search.ValueType, sources ...storage.CaptureSource) storage.UpstreamCaptureField {
	source := storage.CaptureSourceHead
	if len(sources) > 0 {
		source = sources[0]
	}

	return storage.UpstreamCaptureField{
		ID: id, AttributePath: path, Enabled: true, Category: category, Origin: storage.CaptureFieldOriginPlatform,
		CaptureSource: source, ExtractorType: extractor, ExtractorRef: ref, ValueType: valueType,
	}
}

func userField(path string, extractor storage.CaptureExtractorType, ref string, valueType search.ValueType, sources ...storage.CaptureSource) storage.UpstreamCaptureField {
	source := storage.CaptureSourceHead
	if len(sources) > 0 {
		source = sources[0]
	}

	return storage.UpstreamCaptureField{
		ID: "user", AttributePath: path, Enabled: true, Category: storage.CaptureFieldCategoryOptional, Origin: storage.CaptureFieldOriginUser,
		CaptureSource: source, ExtractorType: extractor, ExtractorRef: ref, ValueType: valueType,
	}
}

func requiredCaptureFields() []storage.UpstreamCaptureField {
	return []storage.UpstreamCaptureField{
		platformField("upstream.head.etag", "upstream.etag", storage.CaptureExtractorSDKField, "ETag", storage.CaptureFieldCategoryRequired, search.TypeString),
		platformField("upstream.head.size", "upstream.size", storage.CaptureExtractorSDKField, "ContentLength", storage.CaptureFieldCategoryRequired, search.TypeInteger),
		platformField("upstream.head.last_modified", "upstream.last_modified", storage.CaptureExtractorSDKField, "LastModified", storage.CaptureFieldCategoryRequired, search.TypeTimestamp),
	}
}
