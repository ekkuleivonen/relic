export type ObjectAttributes = {
  upstream?: {
    etag?: string
    size?: number
    last_modified?: string
    storage_class?: string
    header?: {
      content_type?: string
      cache_control?: string
      accept_ranges?: string
    }
    metadata?: Record<string, unknown>
    s3?: Record<string, unknown>
    gcp?: Record<string, unknown>
    b2?: Record<string, unknown>
  }
  [key: string]: unknown
}

export type CatalogObject = {
  id: string
  bucket_id: string
  key: string
  version_id?: string
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
