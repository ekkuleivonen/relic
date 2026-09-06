package s3compat

import (
	"encoding/xml"
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/elei-io/pithosys/packages/storage"
)

type ListedObject struct {
	Key          string
	ETag         string
	Size         int64
	LastModified time.Time
	StorageClass string
}

type ObjectPage struct {
	Objects               []ListedObject
	IsTruncated           bool
	NextMarker            string
	NextContinuationToken string
}

func ParseListObjectsV2(upstream Upstream, response RawHTTPResponse) (ObjectPage, error) {
	if err := validateUpstream(upstream); err != nil {
		return ObjectPage{}, err
	}
	if err := responseError(response); err != nil {
		return ObjectPage{}, err
	}

	return parseListBucketResult(response.Body)
}

func ParseListObjects(upstream Upstream, response RawHTTPResponse) (ObjectPage, error) {
	if err := validateUpstream(upstream); err != nil {
		return ObjectPage{}, err
	}
	if err := responseError(response); err != nil {
		return ObjectPage{}, err
	}

	return parseListBucketResult(response.Body)
}

func AttributesFromListedObject(object ListedObject) storage.ObjectAttributes {
	attributes := map[string]any{}
	if object.ETag != "" {
		attributes["etag"] = object.ETag
	}
	if object.Size != 0 {
		attributes["size"] = object.Size
	}
	if !object.LastModified.IsZero() {
		attributes["last_modified"] = object.LastModified.UTC().Format(time.RFC3339)
	}
	SetS3StorageClass(attributes, object.StorageClass)

	return upstreamAttributes(attributes)
}

func SetS3StorageClass(upstream map[string]any, storageClass string) {
	if storageClass == "" {
		return
	}

	s3 := ensureNestedMap(upstream, "s3")
	s3["storage_class"] = storageClass
}

func parseListBucketResult(body string) (ObjectPage, error) {
	var result listBucketResult
	if err := xml.Unmarshal([]byte(body), &result); err != nil {
		return ObjectPage{}, fmt.Errorf("parse list bucket result: %w", err)
	}

	page := ObjectPage{
		Objects:               make([]ListedObject, 0, len(result.Contents)),
		IsTruncated:           parseXMLBool(result.IsTruncated),
		NextMarker:            result.NextMarker,
		NextContinuationToken: result.NextContinuationToken,
	}
	for _, entry := range result.Contents {
		object, err := listedObjectFromXML(entry)
		if err != nil {
			return ObjectPage{}, err
		}
		page.Objects = append(page.Objects, object)
	}

	return page, nil
}

func listedObjectFromXML(entry listObjectEntry) (ListedObject, error) {
	size, err := strconv.ParseInt(strings.TrimSpace(entry.Size), 10, 64)
	if err != nil {
		return ListedObject{}, fmt.Errorf("parse listed object size for %q: %w", entry.Key, err)
	}

	lastModified, err := time.Parse(time.RFC3339, strings.TrimSpace(entry.LastModified))
	if err != nil {
		return ListedObject{}, fmt.Errorf("parse listed object last modified for %q: %w", entry.Key, err)
	}

	return ListedObject{
		Key:          entry.Key,
		ETag:         strings.TrimSpace(entry.ETag),
		Size:         size,
		LastModified: lastModified.UTC(),
		StorageClass: strings.TrimSpace(entry.StorageClass),
	}, nil
}

func validateUpstream(upstream Upstream) error {
	switch upstream {
	case UpstreamAWS, UpstreamR2, UpstreamB2, UpstreamGCP, UpstreamRustFS:
		return nil
	default:
		return fmt.Errorf("unsupported s3-compatible upstream %q", upstream)
	}
}

func responseError(response RawHTTPResponse) error {
	if response.Status < 400 {
		return nil
	}

	var payload errorResponse
	if err := xml.Unmarshal([]byte(response.Body), &payload); err != nil {
		return fmt.Errorf("upstream returned status %d", response.Status)
	}
	if payload.Code != "" || payload.Message != "" {
		return fmt.Errorf("upstream returned status %d: %s %s", response.Status, payload.Code, payload.Message)
	}

	return fmt.Errorf("upstream returned status %d", response.Status)
}

func parseXMLBool(value string) bool {
	return strings.EqualFold(strings.TrimSpace(value), "true")
}

type listBucketResult struct {
	Contents              []listObjectEntry `xml:"Contents"`
	IsTruncated           string            `xml:"IsTruncated"`
	NextMarker            string            `xml:"NextMarker"`
	NextContinuationToken string            `xml:"NextContinuationToken"`
}

type listObjectEntry struct {
	Key          string `xml:"Key"`
	ETag         string `xml:"ETag"`
	Size         string `xml:"Size"`
	LastModified string `xml:"LastModified"`
	StorageClass string `xml:"StorageClass"`
}

type errorResponse struct {
	Code    string `xml:"Code"`
	Message string `xml:"Message"`
}
