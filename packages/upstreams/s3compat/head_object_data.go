package s3compat

import (
	"net/http"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/elei-io/pithosys/packages/storage"
)

type HeadObjectData struct {
	Output          *s3.HeadObjectOutput
	ResponseHeaders http.Header
}

func HeadObjectDataFromUpstreamAttributes(attributes storage.ObjectAttributes) HeadObjectData {
	upstream, _ := attributes["upstream"].(map[string]any)
	if upstream == nil {
		return HeadObjectData{Output: &s3.HeadObjectOutput{}}
	}

	output := &s3.HeadObjectOutput{}
	if etag, ok := upstream["etag"].(string); ok {
		output.ETag = aws.String(etag)
	}
	if size, ok := upstream["size"].(int64); ok {
		output.ContentLength = aws.Int64(size)
	} else if size, ok := upstream["size"].(int); ok {
		output.ContentLength = aws.Int64(int64(size))
	}
	if lastModified, ok := upstream["last_modified"].(string); ok {
		if parsed, err := time.Parse(time.RFC3339, lastModified); err == nil {
			output.LastModified = aws.Time(parsed)
		}
	}
	if header, ok := upstream["header"].(map[string]any); ok {
		if contentType, ok := header["content_type"].(string); ok {
			output.ContentType = aws.String(contentType)
		}
	}
	if metadata, ok := upstream["metadata"].(map[string]any); ok {
		output.Metadata = map[string]string{}
		for key, value := range metadata {
			if typed, ok := value.(string); ok {
				output.Metadata[key] = typed
			}
		}
	}

	return HeadObjectData{Output: output}
}
