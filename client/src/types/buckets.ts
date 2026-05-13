export type Bucket = {
  id: string
  name: string
  endpoint: string
  region: string
  bucket: string
  key_id: string
  secret_access_key: string
  max_size_bytes: number
  object_count: number
  current_size_bytes: number
  avg_latency_ms: number | null
  probe_sample_count: number
  reachable: boolean
}

export type BucketCreateInput = {
  name: string
  endpoint: string
  region: string
  bucket: string
  key_id: string
  secret_access_key: string
  max_size_bytes: number
}

export type BucketUpdateInput = Partial<
  Pick<
    BucketCreateInput,
    | "name"
    | "endpoint"
    | "region"
    | "bucket"
    | "key_id"
    | "secret_access_key"
    | "max_size_bytes"
  >
>

export type BucketProbeResult = Bucket

export type BucketProbeSample = {
  id: string
  observed_at: string
  success: boolean
  put_ms: number | null
  head_ms: number | null
  get_ms: number | null
  delete_ms: number | null
}
