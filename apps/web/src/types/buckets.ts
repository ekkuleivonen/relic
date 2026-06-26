export type BucketUpstream = "s3"

export type BucketUpstreamConfig = Record<string, unknown>

export type BucketPluginSettings = {
  enabled: boolean
  settings: Record<string, unknown>
}

export type BucketPluginSettingsMap = Record<string, BucketPluginSettings>

export type Bucket = {
  id: string
  name: string
  upstream: BucketUpstream
  endpoint_url: string
  region: string
  bucket_name: string
  prefix: string
  upstream_config: BucketUpstreamConfig
  plugin_settings: BucketPluginSettingsMap
  created_at: string
  updated_at: string
}

export type ListBucketsResponse = {
  buckets: Bucket[]
}

export type CreateBucketInput = {
  name: string
  upstream: BucketUpstream
  endpoint_url: string
  region: string
  bucket_name: string
  prefix: string
  upstream_config: BucketUpstreamConfig
  credentials: Record<string, unknown>
  plugin_settings: BucketPluginSettingsMap
}

export type UpdateBucketInput = {
  name?: string
  endpoint_url?: string
  region?: string
  prefix?: string
  upstream_config?: BucketUpstreamConfig
  credentials?: Record<string, unknown>
  plugin_settings?: BucketPluginSettingsMap
}
