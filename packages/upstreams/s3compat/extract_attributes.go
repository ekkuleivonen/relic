package s3compat

import (
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/s3/types"
	"github.com/ekkuleivonen/relic/packages/search"
	"github.com/ekkuleivonen/relic/packages/storage"
)

func ExtractAttributes(fields []storage.UpstreamCaptureField, head HeadObjectData, tags map[string]string) (storage.ObjectAttributes, error) {
	upstream := map[string]any{}

	for _, field := range fields {
		if !field.Enabled {
			continue
		}

		value, ok, err := extractCaptureFieldValue(field, head, tags)
		if err != nil {
			return nil, err
		}
		if !ok {
			if field.Category == storage.CaptureFieldCategoryRequired {
				return nil, fmt.Errorf("required capture field %q missing", field.AttributePath)
			}
			continue
		}

		coerced, err := coerceCaptureValue(field.ValueType, value)
		if err != nil {
			if field.Category == storage.CaptureFieldCategoryRequired {
				return nil, fmt.Errorf("coerce capture field %q: %w", field.AttributePath, err)
			}
			continue
		}

		if err := setAttributeAtPath(upstream, field.AttributePath, coerced, field); err != nil {
			return nil, err
		}
	}

	pruneEmptyMaps(upstream)

	return storage.ObjectAttributes{"upstream": upstream}, nil
}

func extractCaptureFieldValue(field storage.UpstreamCaptureField, head HeadObjectData, tags map[string]string) (any, bool, error) {
	switch field.CaptureSource {
	case storage.CaptureSourceHead:
		return extractHeadCaptureFieldValue(field, head)
	case storage.CaptureSourceTagging:
		return extractTaggingCaptureFieldValue(field, tags)
	default:
		return nil, false, fmt.Errorf("unsupported capture_source %q", field.CaptureSource)
	}
}

func extractHeadCaptureFieldValue(field storage.UpstreamCaptureField, head HeadObjectData) (any, bool, error) {
	switch field.ExtractorType {
	case storage.CaptureExtractorSDKField:
		extractor, ok := sdkFieldExtractors[field.ExtractorRef]
		if !ok {
			if field.Category == storage.CaptureFieldCategoryRequired {
				return nil, false, fmt.Errorf("unknown sdk_field %q", field.ExtractorRef)
			}
			return nil, false, nil
		}

		return extractor(head.Output)
	case storage.CaptureExtractorResponseHeader:
		if head.ResponseHeaders == nil {
			return nil, false, nil
		}

		value := head.ResponseHeaders.Get(field.ExtractorRef)
		if value == "" {
			return nil, false, nil
		}

		return value, true, nil
	case storage.CaptureExtractorMetadataKey:
		if head.Output == nil || len(head.Output.Metadata) == 0 {
			return nil, false, nil
		}

		value, ok := head.Output.Metadata[field.ExtractorRef]
		if !ok {
			return nil, false, nil
		}

		return value, true, nil
	case storage.CaptureExtractorMetadataAll:
		if head.Output == nil || len(head.Output.Metadata) == 0 {
			return nil, false, nil
		}

		metadata := map[string]any{}
		for key, value := range head.Output.Metadata {
			metadata[key] = value
		}

		return metadata, true, nil
	default:
		return nil, false, fmt.Errorf("unsupported head extractor_type %q", field.ExtractorType)
	}
}

func extractTaggingCaptureFieldValue(field storage.UpstreamCaptureField, tags map[string]string) (any, bool, error) {
	switch field.ExtractorType {
	case storage.CaptureExtractorTagKey:
		if len(tags) == 0 {
			return nil, false, nil
		}

		value, ok := tags[field.ExtractorRef]
		if !ok {
			return nil, false, nil
		}

		return value, true, nil
	case storage.CaptureExtractorTaggingAll:
		if len(tags) == 0 {
			return nil, false, nil
		}

		tagAttributes := map[string]any{}
		for key, value := range tags {
			tagAttributes[key] = value
		}

		return tagAttributes, true, nil
	default:
		return nil, false, fmt.Errorf("unsupported tagging extractor_type %q", field.ExtractorType)
	}
}

type sdkFieldExtractor func(*s3.HeadObjectOutput) (any, bool, error)

var sdkFieldExtractors = map[string]sdkFieldExtractor{
	"ETag": func(output *s3.HeadObjectOutput) (any, bool, error) {
		if output == nil || output.ETag == nil {
			return nil, false, nil
		}

		return aws.ToString(output.ETag), true, nil
	},
	"ContentLength": func(output *s3.HeadObjectOutput) (any, bool, error) {
		if output == nil || output.ContentLength == nil {
			return nil, false, nil
		}

		return aws.ToInt64(output.ContentLength), true, nil
	},
	"LastModified": func(output *s3.HeadObjectOutput) (any, bool, error) {
		if output == nil || output.LastModified == nil {
			return nil, false, nil
		}

		return output.LastModified.UTC().Format(time.RFC3339), true, nil
	},
	"AcceptRanges":       sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.AcceptRanges }),
	"CacheControl":       sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.CacheControl }),
	"ContentType":        sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.ContentType }),
	"ContentDisposition": sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.ContentDisposition }),
	"ContentEncoding":    sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.ContentEncoding }),
	"ContentLanguage":    sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.ContentLanguage }),
	"StorageClass":       sdkEnumField(func(output *s3.HeadObjectOutput) types.StorageClass { return output.StorageClass }),
	"VersionId":          sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.VersionId }),
	"ServerSideEncryption": sdkEnumField(func(output *s3.HeadObjectOutput) types.ServerSideEncryption {
		return output.ServerSideEncryption
	}),
	"SSEKMSKeyId":             sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.SSEKMSKeyId }),
	"SSECustomerAlgorithm":    sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.SSECustomerAlgorithm }),
	"SSECustomerKeyMD5":       sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.SSECustomerKeyMD5 }),
	"WebsiteRedirectLocation": sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.WebsiteRedirectLocation }),
	"Expiration":              sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.Expiration }),
	"ChecksumCRC32":           sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.ChecksumCRC32 }),
	"ChecksumCRC32C":          sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.ChecksumCRC32C }),
	"ChecksumCRC64NVME":       sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.ChecksumCRC64NVME }),
	"ChecksumSHA1":            sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.ChecksumSHA1 }),
	"ChecksumSHA256":          sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.ChecksumSHA256 }),
	"ChecksumSHA512":          sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.ChecksumSHA512 }),
	"ChecksumMD5":             sdkStringField(func(output *s3.HeadObjectOutput) *string { return output.ChecksumMD5 }),
	"BucketKeyEnabled": func(output *s3.HeadObjectOutput) (any, bool, error) {
		if output == nil || output.BucketKeyEnabled == nil {
			return nil, false, nil
		}

		return aws.ToBool(output.BucketKeyEnabled), true, nil
	},
	"ArchiveStatus": sdkEnumField(func(output *s3.HeadObjectOutput) types.ArchiveStatus { return output.ArchiveStatus }),
	"ReplicationStatus": sdkEnumField(func(output *s3.HeadObjectOutput) types.ReplicationStatus {
		return output.ReplicationStatus
	}),
	"ObjectLockMode": sdkEnumField(func(output *s3.HeadObjectOutput) types.ObjectLockMode { return output.ObjectLockMode }),
	"ObjectLockLegalHoldStatus": sdkEnumField(func(output *s3.HeadObjectOutput) types.ObjectLockLegalHoldStatus {
		return output.ObjectLockLegalHoldStatus
	}),
	"ObjectLockRetainUntilDate": func(output *s3.HeadObjectOutput) (any, bool, error) {
		if output == nil || output.ObjectLockRetainUntilDate == nil {
			return nil, false, nil
		}

		return output.ObjectLockRetainUntilDate.UTC().Format(time.RFC3339), true, nil
	},
	"PartsCount": func(output *s3.HeadObjectOutput) (any, bool, error) {
		if output == nil || output.PartsCount == nil {
			return nil, false, nil
		}

		return aws.ToInt32(output.PartsCount), true, nil
	},
	"DeleteMarker": func(output *s3.HeadObjectOutput) (any, bool, error) {
		if output == nil || !aws.ToBool(output.DeleteMarker) {
			return nil, false, nil
		}

		return true, true, nil
	},
}

func sdkStringField(read func(*s3.HeadObjectOutput) *string) sdkFieldExtractor {
	return func(output *s3.HeadObjectOutput) (any, bool, error) {
		if output == nil {
			return nil, false, nil
		}

		value := read(output)
		if value == nil {
			return nil, false, nil
		}

		return aws.ToString(value), true, nil
	}
}

func sdkEnumField[T ~string](read func(*s3.HeadObjectOutput) T) sdkFieldExtractor {
	return func(output *s3.HeadObjectOutput) (any, bool, error) {
		if output == nil {
			return nil, false, nil
		}

		value := read(output)
		if value == "" {
			return nil, false, nil
		}

		return string(value), true, nil
	}
}

func coerceCaptureValue(valueType search.ValueType, value any) (any, error) {
	switch valueType {
	case search.TypeString, search.TypeTimestamp, search.TypeUnknown:
		switch typed := value.(type) {
		case string:
			return typed, nil
		case map[string]any:
			return typed, nil
		default:
			return fmt.Sprint(value), nil
		}
	case search.TypeInteger:
		switch typed := value.(type) {
		case int:
			return int64(typed), nil
		case int32:
			return int64(typed), nil
		case int64:
			return typed, nil
		case float64:
			return int64(typed), nil
		case string:
			parsed, err := strconv.ParseInt(typed, 10, 64)
			if err != nil {
				return nil, err
			}

			return parsed, nil
		default:
			return nil, fmt.Errorf("unsupported integer value %T", value)
		}
	case search.TypeFloat:
		switch typed := value.(type) {
		case float64:
			return typed, nil
		case float32:
			return float64(typed), nil
		case int, int32, int64:
			return float64(reflectInt64(typed)), nil
		case string:
			parsed, err := strconv.ParseFloat(typed, 64)
			if err != nil {
				return nil, err
			}

			return parsed, nil
		default:
			return nil, fmt.Errorf("unsupported float value %T", value)
		}
	case search.TypeBoolean:
		switch typed := value.(type) {
		case bool:
			return typed, nil
		case string:
			parsed, err := strconv.ParseBool(typed)
			if err != nil {
				return nil, err
			}

			return parsed, nil
		default:
			return nil, fmt.Errorf("unsupported boolean value %T", value)
		}
	default:
		return value, nil
	}
}

func reflectInt64(value any) int64 {
	switch typed := value.(type) {
	case int:
		return int64(typed)
	case int32:
		return int64(typed)
	case int64:
		return typed
	default:
		return 0
	}
}

func setAttributeAtPath(root map[string]any, attributePath string, value any, field storage.UpstreamCaptureField) error {
	if !strings.HasPrefix(attributePath, "upstream.") {
		return fmt.Errorf("attribute_path %q must start with upstream.", attributePath)
	}

	switch field.ExtractorType {
	case storage.CaptureExtractorMetadataAll:
		metadata, ok := value.(map[string]any)
		if !ok {
			return fmt.Errorf("metadata_all value must be a map")
		}
		if len(metadata) == 0 {
			return nil
		}
		root["metadata"] = metadata
		return nil
	case storage.CaptureExtractorTaggingAll:
		tagAttributes, ok := value.(map[string]any)
		if !ok {
			return fmt.Errorf("tagging_all value must be a map")
		}
		if len(tagAttributes) == 0 {
			return nil
		}
		root["tag"] = tagAttributes
		return nil
	}

	parts := strings.Split(strings.TrimPrefix(attributePath, "upstream."), ".")
	if len(parts) == 0 || parts[0] == "" {
		return fmt.Errorf("invalid attribute_path %q", attributePath)
	}

	current := root
	for _, part := range parts[:len(parts)-1] {
		nested, ok := current[part].(map[string]any)
		if !ok || nested == nil {
			nested = map[string]any{}
			current[part] = nested
		}
		current = nested
	}
	current[parts[len(parts)-1]] = value

	return nil
}

func pruneEmptyMaps(root map[string]any) {
	for key, value := range root {
		nested, ok := value.(map[string]any)
		if !ok {
			continue
		}
		pruneEmptyMaps(nested)
		if len(nested) == 0 {
			delete(root, key)
		}
	}
}
