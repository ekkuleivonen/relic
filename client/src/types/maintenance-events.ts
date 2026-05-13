export type MaintenanceEventStatus = "succeeded" | "failed" | "skipped"

export type MaintenanceEventRecord = {
  id: string
  job: string
  action: string
  status: MaintenanceEventStatus
  batch_id: string
  bucket_id: string | null
  blob_id: string | null
  duration_ms: number | null
  metadata: Record<string, unknown>
  created_at: string
}

export type MaintenanceEventsQuery = {
  job?: string
  action?: string
  status?: MaintenanceEventStatus
  batch_id?: string
  bucket_id?: string
  blob_id?: string
  created_after?: string
  created_before?: string
  limit?: number
  offset?: number
}

export type MaintenanceEventsResponse = {
  items: MaintenanceEventRecord[]
  total: number
  limit: number
  offset: number
}
