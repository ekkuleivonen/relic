import type { User } from "@/types/users"

export type EventStatus = "succeeded" | "failed"

export type EventRecord = {
  id: string
  source: string
  operation: string
  status: EventStatus
  actor_user_id: string | null
  actor: User | null
  request_id: string | null
  file_ids: string[]
  folder_ids: string[]
  blob_ids: string[]
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export type EventsQuery = {
  source?: string
  operation?: string
  status?: EventStatus
  actor_user_id?: string
  request_id?: string
  created_after?: string
  created_before?: string
  limit?: number
  offset?: number
}

export type EventsResponse = {
  items: EventRecord[]
  total: number
  limit: number
  offset: number
}
