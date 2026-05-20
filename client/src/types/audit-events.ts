import type { User } from "@/types/users"

export type AuditEventStatus = "succeeded" | "failed" | "skipped"

export type AuditEventRecord = {
  id: string
  operation: string
  status: AuditEventStatus
  actor_id: string | null
  actor: User | null
  request_id: string | null
  job: string | null
  batch_id: string | null
  storage_backend_id: string | null
  blob_id: string | null
  duration_ms: number | null
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export type AuditEventsQuery = {
  operation?: string
  status?: AuditEventStatus
  actor_id?: string
  request_id?: string
  job?: string
  batch_id?: string
  storage_backend_id?: string
  blob_id?: string
  created_after?: string
  created_before?: string
  limit?: number
  offset?: number
}

export type AuditEventsResponse = {
  items: AuditEventRecord[]
  total: number
  limit: number
  offset: number
}
