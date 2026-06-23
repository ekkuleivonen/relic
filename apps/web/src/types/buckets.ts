export type BucketProvider = "s3"

export type BucketProviderConfig = Record<string, unknown>

export type BucketPluginSettings = {
  enabled: boolean
  settings: Record<string, unknown>
}

export type BucketPluginSettingsMap = Record<string, BucketPluginSettings>

export type Bucket = {
  id: string
  name: string
  provider: BucketProvider
  endpoint_url: string
  region: string
  bucket_name: string
  prefix: string
  provider_config: BucketProviderConfig
  plugin_settings: BucketPluginSettingsMap
  created_at: string
  updated_at: string
}

export type ListBucketsResponse = {
  buckets: Bucket[]
}

export type CreateBucketInput = {
  name: string
  provider: BucketProvider
  endpoint_url: string
  region: string
  bucket_name: string
  prefix: string
  provider_config: BucketProviderConfig
  credentials: Record<string, unknown>
  plugin_settings: BucketPluginSettingsMap
}

export type UpdateBucketInput = {
  name?: string
  endpoint_url?: string
  region?: string
  prefix?: string
  provider_config?: BucketProviderConfig
  credentials?: Record<string, unknown>
  plugin_settings?: BucketPluginSettingsMap
}
