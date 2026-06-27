export type UserAttributeValueType =
  | "string"
  | "integer"
  | "float"
  | "boolean"
  | "timestamp"

export const userAttributeValueTypes: Array<{
  value: UserAttributeValueType
  label: string
}> = [
  { value: "string", label: "String" },
  { value: "integer", label: "Integer" },
  { value: "float", label: "Float" },
  { value: "boolean", label: "Boolean" },
  { value: "timestamp", label: "Timestamp" },
]

export type ObjectAttributes = {
  core?: {
    object_id?: string
    first_seen_at?: string
    last_seen_at?: string
  }
  upstream?: {
    etag?: string
    size?: number
    last_modified?: string
    header?: {
      content_type?: string
      cache_control?: string
      accept_ranges?: string
    }
    metadata?: Record<string, unknown>
    s3?: {
      version_id?: string
      storage_class?: string
      [key: string]: unknown
    }
    gcp?: Record<string, unknown>
    b2?: Record<string, unknown>
  }
  user?: Record<string, unknown>
  [key: string]: unknown
}

export type CatalogObject = {
  id: string
  bucket_id: string
  key: string
  attributes: ObjectAttributes
  attribute_provenance: Record<string, string>
  first_seen_at: string
  last_seen_at: string
  created_at: string
  updated_at: string
}

export type ListObjectsResponse = {
  objects: CatalogObject[]
}

export type ListObjectsParams = {
  bucketId?: string
  prefix?: string
  contentType?: string
  keyContains?: string
  limit?: number
  offset?: number
}

export type PatchObjectAttributesInput = {
  set?: Record<string, unknown>
  delete?: string[]
}
