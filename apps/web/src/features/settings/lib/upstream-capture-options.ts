import type {
  CaptureExtractorType,
  CaptureSource,
  CaptureValueType,
} from "@/types/upstream-capture"

export const USER_CAPTURE_SOURCES: CaptureSource[] = ["head", "tagging"]

export const USER_VALUE_TYPES: CaptureValueType[] = [
  "string",
  "integer",
  "float",
  "boolean",
  "timestamp",
]

export const USER_EXTRACTOR_TYPES: Record<CaptureSource, CaptureExtractorType[]> =
  {
    head: ["response_header", "metadata_key"],
    tagging: ["tag_key"],
  }

export function extractorTypesForSource(
  captureSource: CaptureSource
): CaptureExtractorType[] {
  return USER_EXTRACTOR_TYPES[captureSource]
}

export function defaultExtractorType(
  captureSource: CaptureSource
): CaptureExtractorType {
  return USER_EXTRACTOR_TYPES[captureSource][0]
}

export function formatCaptureSource(value: CaptureSource) {
  switch (value) {
    case "head":
      return "HEAD"
    case "tagging":
      return "Tagging"
  }
}

export function formatExtractorType(value: CaptureExtractorType) {
  switch (value) {
    case "sdk_field":
      return "SDK field"
    case "response_header":
      return "Response header"
    case "metadata_key":
      return "Metadata key"
    case "metadata_all":
      return "All metadata"
    case "tag_key":
      return "Tag key"
    case "tagging_all":
      return "All tags"
  }
}

export function extractorRefHint(
  extractorType: CaptureExtractorType
): string {
  switch (extractorType) {
    case "response_header":
      return "x-acme-deployment-id"
    case "metadata_key":
      return "cost-center"
    case "tag_key":
      return "environment"
    default:
      return ""
  }
}

export function extractorRefHelp(extractorType: CaptureExtractorType): string {
  switch (extractorType) {
    case "response_header":
      return "HTTP header name from the S3 HEAD response."
    case "metadata_key":
      return "User metadata key without the x-amz-meta- prefix."
    case "tag_key":
      return "Object tag key from GetObjectTagging."
    default:
      return ""
  }
}
