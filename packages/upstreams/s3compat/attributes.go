package s3compat

import (
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/ekkuleivonen/relic/packages/storage"
)

type Upstream string

const (
	UpstreamAWS    Upstream = "aws"
	UpstreamR2     Upstream = "r2"
	UpstreamB2     Upstream = "b2"
	UpstreamGCP    Upstream = "gcp"
	UpstreamRustFS Upstream = "rustfs"
)

type RawHTTPResponse struct {
	Status     int         `json:"status"`
	Headers    [][2]string `json:"headers"`
	Body       string      `json:"body"`
	BodyBase64 string      `json:"body_base64"`
}

func AttributesFromHead(upstream Upstream, response RawHTTPResponse) (storage.ObjectAttributes, error) {
	switch upstream {
	case UpstreamAWS:
		return awsAttributesFromHead(response)
	case UpstreamR2:
		return r2AttributesFromHead(response)
	case UpstreamB2:
		return b2AttributesFromHead(response)
	case UpstreamGCP:
		return gcpAttributesFromHead(response)
	case UpstreamRustFS:
		return rustfsAttributesFromHead(response)
	default:
		return nil, fmt.Errorf("unsupported s3-compatible upstream %q", upstream)
	}
}

func awsAttributesFromHead(response RawHTTPResponse) (storage.ObjectAttributes, error) {
	return s3AttributesFromHead(response)
}

func r2AttributesFromHead(response RawHTTPResponse) (storage.ObjectAttributes, error) {
	return s3AttributesFromHead(response)
}

func b2AttributesFromHead(response RawHTTPResponse) (storage.ObjectAttributes, error) {
	headers := newHeaderMap(response.Headers)
	attributes, err := commonAttributesFromHead(headers)
	if err != nil {
		return nil, err
	}
	addS3Attributes(attributes, headers)
	if err := addB2Attributes(attributes, headers); err != nil {
		return nil, err
	}

	return upstreamAttributes(attributes), nil
}

func gcpAttributesFromHead(response RawHTTPResponse) (storage.ObjectAttributes, error) {
	headers := newHeaderMap(response.Headers)
	attributes, err := commonAttributesFromHead(headers)
	if err != nil {
		return nil, err
	}
	if err := addGCPAttributes(attributes, headers); err != nil {
		return nil, err
	}

	return upstreamAttributes(attributes), nil
}

func rustfsAttributesFromHead(response RawHTTPResponse) (storage.ObjectAttributes, error) {
	return s3AttributesFromHead(response)
}

func s3AttributesFromHead(response RawHTTPResponse) (storage.ObjectAttributes, error) {
	headers := newHeaderMap(response.Headers)
	attributes, err := commonAttributesFromHead(headers)
	if err != nil {
		return nil, err
	}
	addS3Attributes(attributes, headers)

	return upstreamAttributes(attributes), nil
}

func upstreamAttributes(attributes map[string]any) storage.ObjectAttributes {
	return storage.ObjectAttributes{
		"upstream": attributes,
	}
}

func commonAttributesFromHead(headers headerMap) (map[string]any, error) {
	attributes := map[string]any{}

	if etag, ok := headers.first("etag"); ok {
		attributes["etag"] = etag
	}
	if contentLength, ok := headers.first("content-length"); ok {
		size, err := strconv.ParseInt(contentLength, 10, 64)
		if err != nil {
			return nil, fmt.Errorf("parse content-length: %w", err)
		}
		attributes["size"] = size
	}
	if lastModified, ok := headers.first("last-modified"); ok {
		parsed, err := http.ParseTime(lastModified)
		if err != nil {
			return nil, fmt.Errorf("parse last-modified: %w", err)
		}
		attributes["last_modified"] = parsed.UTC().Format(time.RFC3339)
	}

	headerAttributes := map[string]any{}
	copyHeader(headers, headerAttributes, "accept-ranges", "accept_ranges")
	copyHeader(headers, headerAttributes, "cache-control", "cache_control")
	copyHeader(headers, headerAttributes, "content-type", "content_type")
	if len(headerAttributes) > 0 {
		attributes["header"] = headerAttributes
	}

	metadata := metadataAttributes(headers, "x-amz-meta-")
	if len(metadata) > 0 {
		attributes["metadata"] = metadata
	}

	return attributes, nil
}

func addS3Attributes(attributes map[string]any, headers headerMap) {
	s3 := map[string]any{}
	copyHeader(headers, s3, "x-amz-storage-class", "storage_class")
	copyHeader(headers, s3, "x-amz-version-id", "version_id")
	if len(s3) > 0 {
		attributes["s3"] = s3
	}
}

func addB2Attributes(attributes map[string]any, headers headerMap) error {
	b2 := map[string]any{}

	if value, ok := headers.first("x-backblaze-live-read-enabled"); ok {
		enabled, err := strconv.ParseBool(value)
		if err != nil {
			return fmt.Errorf("parse x-backblaze-live-read-enabled: %w", err)
		}
		b2["live_read_enabled"] = enabled
	}
	if value, ok := headers.first("x-backblaze-live-read-part-size"); ok {
		partSize, err := strconv.ParseInt(value, 10, 64)
		if err != nil {
			return fmt.Errorf("parse x-backblaze-live-read-part-size: %w", err)
		}
		b2["live_read_part_size"] = partSize
	}
	if len(b2) > 0 {
		attributes["b2"] = b2
	}

	return nil
}

func addGCPAttributes(attributes map[string]any, headers headerMap) error {
	gcp := map[string]any{}
	copyHeader(headers, gcp, "x-goog-generation", "generation")
	copyHeader(headers, gcp, "x-goog-metageneration", "metageneration")
	copyHeader(headers, gcp, "x-goog-stored-content-encoding", "stored_content_encoding")
	copyHeader(headers, gcp, "x-goog-storage-class", "storage_class")

	if value, ok := headers.first("x-goog-stored-content-length"); ok {
		length, err := strconv.ParseInt(value, 10, 64)
		if err != nil {
			return fmt.Errorf("parse x-goog-stored-content-length: %w", err)
		}
		gcp["stored_content_length"] = length
	}
	if values := headers.all("x-goog-hash"); len(values) > 0 {
		gcp["hash"] = values
	}
	if len(gcp) > 0 {
		attributes["gcp"] = gcp
	}

	return nil
}

func copyHeader(headers headerMap, target map[string]any, headerName string, attributeName string) {
	if value, ok := headers.first(headerName); ok {
		target[attributeName] = value
	}
}

func metadataAttributes(headers headerMap, prefix string) map[string]any {
	metadata := map[string]any{}
	for _, pair := range headers.pairs {
		name := strings.ToLower(pair[0])
		if !strings.HasPrefix(name, prefix) {
			continue
		}

		metadata[strings.TrimPrefix(name, prefix)] = pair[1]
	}

	return metadata
}

type headerMap struct {
	pairs  [][2]string
	values map[string][]string
}

func newHeaderMap(pairs [][2]string) headerMap {
	values := map[string][]string{}
	for _, pair := range pairs {
		name := strings.ToLower(pair[0])
		values[name] = append(values[name], pair[1])
	}

	return headerMap{
		pairs:  pairs,
		values: values,
	}
}

func (h headerMap) first(name string) (string, bool) {
	values := h.values[strings.ToLower(name)]
	if len(values) == 0 {
		return "", false
	}

	return values[0], true
}

func (h headerMap) all(name string) []string {
	values := h.values[strings.ToLower(name)]
	return append([]string(nil), values...)
}
