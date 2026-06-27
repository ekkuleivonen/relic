export type BucketUpstream = "s3"

export type BucketUpstreamConfig = Record<string, unknown>

export type BucketJetStreamConfig = {
  url: string
  stream: string
  subject: string
  consumer?: string
}

export type BucketScanConfig = {
  enabled: boolean
  interval?: string
}

export type BucketRelicConfig = {
  scan?: BucketScanConfig
}

export type Bucket = {
  id: string
  name: string
  upstream: BucketUpstream
  endpoint_url: string
  region: string
  bucket_name: string
  prefix: string
  upstream_config: BucketUpstreamConfig
  relic_config: BucketRelicConfig
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
  relic_config: BucketRelicConfig
}

export type UpdateBucketInput = {
  name?: string
  endpoint_url?: string
  region?: string
  prefix?: string
  upstream_config?: BucketUpstreamConfig
  credentials?: Record<string, unknown>
  relic_config?: BucketRelicConfig
}
