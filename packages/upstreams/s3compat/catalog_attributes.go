package s3compat

import (
	"context"
	"errors"
	"fmt"

	"github.com/aws/smithy-go"
	"github.com/ekkuleivonen/relic/packages/storage"
)

func FetchCatalogAttributes(ctx context.Context, client ObjectClient, input HeadObjectInput, fields []storage.UpstreamCaptureField) (storage.ObjectAttributes, error) {
	head, err := client.HeadObject(ctx, input)
	if err != nil {
		return nil, err
	}

	var tags map[string]string
	if storage.CaptureFieldsNeedTagging(fields) {
		tags, err = client.GetObjectTagging(ctx, input)
		if err != nil {
			if IsGetObjectTaggingUnsupported(err) {
				tags = nil
			} else {
				return nil, fmt.Errorf("get object tagging for %q: %w", input.Key, err)
			}
		}
	}

	return ExtractAttributes(fields, head, tags)
}

func MergeTagAttributes(attributes storage.ObjectAttributes, tags map[string]string) storage.ObjectAttributes {
	if len(tags) == 0 {
		return attributes
	}

	upstream, ok := attributes["upstream"].(map[string]any)
	if !ok || upstream == nil {
		upstream = map[string]any{}
		attributes = storage.ObjectAttributes{"upstream": upstream}
	}

	tagAttributes := map[string]any{}
	for key, value := range tags {
		tagAttributes[key] = value
	}
	upstream["tag"] = tagAttributes

	return attributes
}

func IsGetObjectTaggingUnsupported(err error) bool {
	if err == nil {
		return false
	}

	var apiErr smithy.APIError
	if !errors.As(err, &apiErr) {
		return false
	}

	switch apiErr.ErrorCode() {
	case "NotImplemented", "NotSupported", "MethodNotAllowed", "XNotImplemented":
		return true
	default:
		return false
	}
}
