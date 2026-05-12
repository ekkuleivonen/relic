export const bucketTiers = [
  { value: 1, label: "Hot" },
  { value: 2, label: "Warm" },
  { value: 3, label: "Cold" },
  { value: 4, label: "Frozen" },
] as const

export type BucketTier = (typeof bucketTiers)[number]["value"]

export type Bucket = {
  id: string
  name: string
  endpoint: string
  region: string
  bucket: string
  key_id: string
  secret_access_key: string
  tier: BucketTier
  max_size_bytes: number
  object_count: number
  current_size_bytes: number
  probe_latency_put_ms: number | null
  probe_latency_head_ms: number | null
  probe_latency_get_ms: number | null
  probe_latency_delete_ms: number | null
}

export type BucketCreateInput = {
  name: string
  endpoint: string
  region: string
  bucket: string
  key_id: string
  secret_access_key: string
  tier: BucketTier
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
    | "tier"
    | "max_size_bytes"
  >
>

export type BucketProbeResult = Bucket & {
  reachable: boolean
}
