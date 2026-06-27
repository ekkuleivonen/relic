export type CaptureFieldCategory = "required" | "optional"

export type CaptureFieldOrigin = "platform" | "user"

export type CaptureSource = "head" | "tagging"

export type CaptureExtractorType =
  | "sdk_field"
  | "response_header"
  | "metadata_key"
  | "metadata_all"
  | "tag_key"
  | "tagging_all"

export type CaptureValueType =
  | "string"
  | "integer"
  | "float"
  | "boolean"
  | "timestamp"
  | "json"
  | "unknown"

export type UpstreamCaptureField = {
  id: string
  attribute_path: string
  enabled: boolean
  category: CaptureFieldCategory
  origin: CaptureFieldOrigin
  capture_source: CaptureSource
  extractor_type: CaptureExtractorType
  extractor_ref: string
  value_type: CaptureValueType
  created_at: string
  updated_at: string
}

export type CreateUpstreamCaptureFieldInput = {
  attribute_path: string
  enabled?: boolean
  capture_source: CaptureSource
  extractor_type: CaptureExtractorType
  extractor_ref: string
  value_type: CaptureValueType
}

export type UpdateUpstreamCaptureFieldInput = {
  attribute_path?: string
  enabled?: boolean
  capture_source?: CaptureSource
  extractor_type?: CaptureExtractorType
  extractor_ref?: string
  value_type?: CaptureValueType
}
