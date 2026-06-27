package s3compat

import (
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/s3/types"
	"github.com/ekkuleivonen/relic/packages/storage"
)

func ObjectPageFromListObjectsV2Output(output *s3.ListObjectsV2Output) ObjectPage {
	if output == nil {
		return ObjectPage{}
	}

	return ObjectPage{
		Objects:               listedObjectsFromSDKObjects(output.Contents),
		IsTruncated:           aws.ToBool(output.IsTruncated),
		NextContinuationToken: aws.ToString(output.NextContinuationToken),
	}
}

func ObjectPageFromListObjectsOutput(output *s3.ListObjectsOutput) ObjectPage {
	if output == nil {
		return ObjectPage{}
	}

	return ObjectPage{
		Objects:     listedObjectsFromSDKObjects(output.Contents),
		IsTruncated: aws.ToBool(output.IsTruncated),
		NextMarker:  aws.ToString(output.NextMarker),
	}
}

func AttributesFromHeadObjectOutput(output *s3.HeadObjectOutput) storage.ObjectAttributes {
	if output == nil {
		return upstreamAttributes(map[string]any{})
	}

	attributes := map[string]any{}
	if output.ETag != nil {
		attributes["etag"] = aws.ToString(output.ETag)
	}
	if output.ContentLength != nil {
		attributes["size"] = aws.ToInt64(output.ContentLength)
	}
	if output.LastModified != nil {
		attributes["last_modified"] = output.LastModified.UTC().Format(time.RFC3339)
	}

	header := ensureNestedMap(attributes, "header")
	copySDKString(output.AcceptRanges, header, "accept_ranges")
	copySDKString(output.CacheControl, header, "cache_control")
	copySDKString(output.ContentType, header, "content_type")
	copySDKString(output.ContentDisposition, header, "content_disposition")
	copySDKString(output.ContentEncoding, header, "content_encoding")
	copySDKString(output.ContentLanguage, header, "content_language")
	if len(header) == 0 {
		delete(attributes, "header")
	}

	if len(output.Metadata) > 0 {
		metadata := map[string]any{}
		for key, value := range output.Metadata {
			metadata[key] = value
		}
		attributes["metadata"] = metadata
	}

	s3Attributes := ensureNestedMap(attributes, "s3")
	copySDKEnum(output.StorageClass, s3Attributes, "storage_class")
	copySDKString(output.VersionId, s3Attributes, "version_id")
	copySDKEnum(output.ServerSideEncryption, s3Attributes, "server_side_encryption")
	copySDKString(output.SSEKMSKeyId, s3Attributes, "sse_kms_key_id")
	copySDKString(output.SSECustomerAlgorithm, s3Attributes, "sse_customer_algorithm")
	copySDKString(output.SSECustomerKeyMD5, s3Attributes, "sse_customer_key_md5")
	copySDKString(output.WebsiteRedirectLocation, s3Attributes, "website_redirect_location")
	copySDKString(output.Expiration, s3Attributes, "expiration")
	copySDKString(output.ChecksumCRC32, s3Attributes, "checksum_crc32")
	copySDKString(output.ChecksumCRC32C, s3Attributes, "checksum_crc32c")
	copySDKString(output.ChecksumCRC64NVME, s3Attributes, "checksum_crc64nvme")
	copySDKString(output.ChecksumSHA1, s3Attributes, "checksum_sha1")
	copySDKString(output.ChecksumSHA256, s3Attributes, "checksum_sha256")
	copySDKString(output.ChecksumSHA512, s3Attributes, "checksum_sha512")
	copySDKString(output.ChecksumMD5, s3Attributes, "checksum_md5")
	copySDKBool(output.BucketKeyEnabled, s3Attributes, "bucket_key_enabled")
	copySDKEnum(output.ArchiveStatus, s3Attributes, "archive_status")
	copySDKEnum(output.ReplicationStatus, s3Attributes, "replication_status")
	copySDKEnum(output.ObjectLockMode, s3Attributes, "object_lock_mode")
	copySDKEnum(output.ObjectLockLegalHoldStatus, s3Attributes, "object_lock_legal_hold_status")
	if output.ObjectLockRetainUntilDate != nil {
		s3Attributes["object_lock_retain_until_date"] = output.ObjectLockRetainUntilDate.UTC().Format(time.RFC3339)
	}
	if output.PartsCount != nil {
		s3Attributes["parts_count"] = aws.ToInt32(output.PartsCount)
	}
	if aws.ToBool(output.DeleteMarker) {
		s3Attributes["delete_marker"] = true
	}
	if len(s3Attributes) == 0 {
		delete(attributes, "s3")
	}

	return upstreamAttributes(attributes)
}

func listedObjectsFromSDKObjects(objects []types.Object) []ListedObject {
	listed := make([]ListedObject, 0, len(objects))
	for _, object := range objects {
		listed = append(listed, ListedObject{
			Key:          aws.ToString(object.Key),
			ETag:         aws.ToString(object.ETag),
			Size:         aws.ToInt64(object.Size),
			LastModified: sdkTime(object.LastModified),
			StorageClass: string(object.StorageClass),
		})
	}

	return listed
}

func copySDKString(value *string, target map[string]any, key string) {
	if value != nil {
		target[key] = aws.ToString(value)
	}
}

func copySDKBool(value *bool, target map[string]any, key string) {
	if value == nil {
		return
	}

	target[key] = *value
}

func copySDKEnum[T ~string](value T, target map[string]any, key string) {
	if value == "" {
		return
	}

	target[key] = string(value)
}

func sdkTime(value *time.Time) time.Time {
	if value == nil {
		return time.Time{}
	}

	return value.UTC()
}

func ensureNestedMap(parent map[string]any, key string) map[string]any {
	if existing, ok := parent[key].(map[string]any); ok && existing != nil {
		return existing
	}

	nested := map[string]any{}
	parent[key] = nested

	return nested
}
