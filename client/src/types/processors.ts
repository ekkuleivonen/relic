export type Processor = {
  id: string
  name: string
  kind: string
  enabled: boolean
  source: "seed" | "admin"
  subscribed_event_types: string[]
  config: Record<string, unknown>
  last_committed_offset: number
  last_committed_at: string | null
  last_failed_event_id: string | null
  last_failed_at: string | null
  last_error_class: string | null
  last_error_message: string | null
  head_offset: number
  pending_count: number
  created_at: string
  updated_at: string
}

export type ProcessorListResponse = {
  items: Processor[]
  total: number
  limit: number
  offset: number
}

export type ProcessorSubstrate = {
  kind: string
}

export type ProcessorSubstratesResponse = {
  items: ProcessorSubstrate[]
}

export type ProcessorCreateInput = {
  name: string
  kind: string
  enabled?: boolean
  subscribed_event_types?: string[]
  config?: Record<string, unknown>
}

export type ProcessorUpdateInput = {
  enabled?: boolean
  subscribed_event_types?: string[]
  config?: Record<string, unknown>
}

export type ProcessorRewindInput = {
  target_offset: number
  reason: string
}

export type ProcessorSkipInput = {
  event_id: string
  reason: string
}
