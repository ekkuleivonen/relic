export type BucketEventState =
  | "pending"
  | "processed"
  | "skipped"
  | "failed"

export type BucketEventCategory =
  | "created"
  | "removed"
  | "metadata_changed"
  | "other"

export type BucketEventTransport = "jetstream"

export type BucketEventPayload = Record<string, unknown>

export type BucketEvent = {
  id: string
  bucket_id: string
  event_name: string
  object_key: string
  envelope: BucketEventPayload
  dedupe_key: string
  transport: BucketEventTransport
  state: BucketEventState
  event_time?: string
  received_at: string
  processed_at?: string
  error_message?: string
  created_at: string
  updated_at: string
}

export type ListBucketEventsParams = {
  bucketId?: string
  state?: BucketEventState
  category?: BucketEventCategory
  receivedAfter?: string
  receivedBefore?: string
  limit?: number
  offset?: number
}

export type ListBucketEventsResponse = {
  bucket_events: BucketEvent[]
  total: number
  limit: number
  offset: number
}
