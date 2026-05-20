export type StorageBackendKind = "s3" | "filesystem" | "azure_blob" | "gcs"

export type StorageBackend = {
  id: string
  name: string
  endpoint: string
  region: string
  namespace: string
  /** Masked on read (last four characters visible). */
  key_id: string
  /** Always masked on read; supply a new value via update to rotate. */
  secret_access_key: string
  max_size_bytes: number
  kind: StorageBackendKind
  object_count: number
  current_size_bytes: number
  avg_latency_ms: number | null
  probe_sample_count: number
  reachable: boolean
}

export type StorageBackendCreateInput = {
  name: string
  endpoint: string
  region?: string
  namespace: string
  key_id?: string
  secret_access_key?: string
  max_size_bytes: number
  kind: StorageBackendKind
}

export type StorageBackendUpdateInput = Partial<
  Pick<
    StorageBackendCreateInput,
    | "name"
    | "endpoint"
    | "region"
    | "namespace"
    | "key_id"
    | "secret_access_key"
    | "max_size_bytes"
    | "kind"
  >
>

export type StorageBackendProbeResult = StorageBackend

export type StorageBackendProbeSample = {
  id: string
  observed_at: string
  success: boolean
  put_ms: number | null
  head_ms: number | null
  get_ms: number | null
  delete_ms: number | null
}

export type DrainStorageBackendResponse = {
  moved: number
  skipped: number
  failed: number
  scanned: number
}
