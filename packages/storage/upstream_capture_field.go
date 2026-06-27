package storage

import (
	"fmt"
	"strings"
	"time"

	"github.com/ekkuleivonen/relic/packages/search"
)

type CaptureFieldCategory string

const (
	CaptureFieldCategoryRequired CaptureFieldCategory = "required"
	CaptureFieldCategoryOptional CaptureFieldCategory = "optional"
)

type CaptureFieldOrigin string

const (
	CaptureFieldOriginPlatform CaptureFieldOrigin = "platform"
	CaptureFieldOriginUser     CaptureFieldOrigin = "user"
)

type CaptureSource string

const (
	CaptureSourceHead    CaptureSource = "head"
	CaptureSourceTagging CaptureSource = "tagging"
)

type CaptureExtractorType string

const (
	CaptureExtractorSDKField       CaptureExtractorType = "sdk_field"
	CaptureExtractorResponseHeader CaptureExtractorType = "response_header"
	CaptureExtractorMetadataKey    CaptureExtractorType = "metadata_key"
	CaptureExtractorMetadataAll    CaptureExtractorType = "metadata_all"
	CaptureExtractorTagKey         CaptureExtractorType = "tag_key"
	CaptureExtractorTaggingAll     CaptureExtractorType = "tagging_all"
)

type UpstreamCaptureField struct {
	ID            string
	AttributePath string
	Enabled       bool
	Category      CaptureFieldCategory
	Origin        CaptureFieldOrigin
	CaptureSource CaptureSource
	ExtractorType CaptureExtractorType
	ExtractorRef  string
	ValueType     search.ValueType
	CreatedAt     time.Time
	UpdatedAt     time.Time
}

type UpstreamCaptureFieldSeed struct {
	ID            string
	AttributePath string
	Enabled       bool
	Category      CaptureFieldCategory
	CaptureSource CaptureSource
	ExtractorType CaptureExtractorType
	ExtractorRef  string
	ValueType     search.ValueType
}

type CreateUpstreamCaptureFieldParams struct {
	AttributePath string
	Enabled       bool
	CaptureSource CaptureSource
	ExtractorType CaptureExtractorType
	ExtractorRef  string
	ValueType     search.ValueType
}

type UpdateUpstreamCaptureFieldParams struct {
	AttributePath *string
	Enabled       *bool
	CaptureSource *CaptureSource
	ExtractorType *CaptureExtractorType
	ExtractorRef  *string
	ValueType     *search.ValueType
}

func ValidateUpstreamCaptureAttributePath(path string) error {
	path = strings.TrimSpace(path)
	if path == "" {
		return fmt.Errorf("attribute_path is required")
	}
	if !strings.HasPrefix(path, "upstream.") {
		return fmt.Errorf("attribute_path must start with upstream.")
	}
	if strings.Contains(path, "..") {
		return fmt.Errorf("attribute_path must not contain ..")
	}

	remainder := strings.TrimPrefix(path, "upstream.")
	if remainder == "" {
		return fmt.Errorf("attribute_path must include a field after upstream.")
	}

	for _, segment := range strings.Split(remainder, ".") {
		if segment == "" {
			return fmt.Errorf("attribute_path must not contain empty segments")
		}
	}

	return nil
}

func ValidateUpstreamCaptureExtractor(extractorType CaptureExtractorType, extractorRef string, origin CaptureFieldOrigin) error {
	extractorRef = strings.TrimSpace(extractorRef)
	if extractorRef == "" {
		return fmt.Errorf("extractor_ref is required")
	}

	switch extractorType {
	case CaptureExtractorSDKField:
		if origin == CaptureFieldOriginUser {
			return fmt.Errorf("sdk_field extractors are platform-only")
		}
	case CaptureExtractorResponseHeader:
		if strings.Contains(extractorRef, "..") {
			return fmt.Errorf("extractor_ref must not contain ..")
		}
	case CaptureExtractorMetadataKey, CaptureExtractorTagKey:
		if strings.Contains(extractorRef, "..") {
			return fmt.Errorf("extractor_ref must not contain ..")
		}
	case CaptureExtractorMetadataAll, CaptureExtractorTaggingAll:
		if extractorRef != "*" {
			return fmt.Errorf("extractor_ref must be * for %s", extractorType)
		}
	default:
		return fmt.Errorf("unsupported extractor_type %q", extractorType)
	}

	return nil
}

func NormalizeCaptureExtractorRef(extractorType CaptureExtractorType, extractorRef string) string {
	extractorRef = strings.TrimSpace(extractorRef)
	if extractorType == CaptureExtractorResponseHeader {
		return strings.ToLower(extractorRef)
	}

	return extractorRef
}

func CaptureFieldsNeedTagging(fields []UpstreamCaptureField) bool {
	for _, field := range fields {
		if field.Enabled && field.CaptureSource == CaptureSourceTagging {
			return true
		}
	}

	return false
}
