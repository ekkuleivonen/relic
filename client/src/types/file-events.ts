import type { User } from "@/types/users"

export type FileEventStatus = "succeeded" | "failed"

export type FileEventRecord = {
  id: string
  offset: number
  schema_version: number
  event_type: string
  status: FileEventStatus
  actor_id: string | null
  actor: User | null
  request_id: string | null
  idempotency_key: string | null
  file_id: string | null
  folder_id: string | null
  payload: Record<string, unknown>
  created_at: string
}

export type FileEventsQuery = {
  event_type?: string
  status?: FileEventStatus
  actor_id?: string
  request_id?: string
  file_id?: string
  folder_id?: string
  created_after?: string
  created_before?: string
  limit?: number
  offset?: number
}

export type FileEventsResponse = {
  items: FileEventRecord[]
  total: number
  limit: number
  offset: number
}
