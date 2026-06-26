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

	header := map[string]any{}
	copySDKString(output.AcceptRanges, header, "accept_ranges")
	copySDKString(output.CacheControl, header, "cache_control")
	copySDKString(output.ContentType, header, "content_type")
	if len(header) > 0 {
		attributes["header"] = header
	}

	if len(output.Metadata) > 0 {
		metadata := map[string]any{}
		for key, value := range output.Metadata {
			metadata[key] = value
		}
		attributes["metadata"] = metadata
	}

	s3Attributes := map[string]any{}
	if output.StorageClass != "" {
		s3Attributes["storage_class"] = string(output.StorageClass)
	}
	copySDKString(output.VersionId, s3Attributes, "version_id")
	if len(s3Attributes) > 0 {
		attributes["s3"] = s3Attributes
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

func sdkTime(value *time.Time) time.Time {
	if value == nil {
		return time.Time{}
	}

	return value.UTC()
}
