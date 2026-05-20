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

export const AUDIT_JOB_OPTIONS = [
  "purge_dereferenced_blobs",
  "demote_pressured_buckets",
  "drain_storage_backend",
  "promote_recently_accessed",
  "storage_backend_probe",
  "trim_storage_backend_probes",
  "trim_audit_events",
  "trim_filesystem_events",
  "abort_incomplete_multipart_uploads",
] as const

export const AUDIT_OPERATION_OPTIONS = [
  "access_key.created",
  "access_key.deleted",
  "access_key.revoked",
  "audit_event.trimmed",
  "auth.login.failed",
  "auth.login.succeeded",
  "auth.logout",
  "auth.bearer.failed",
  "blob.demoted",
  "blob.demotion_failed",
  "blob.demotion_skipped",
  "blob.drain_failed",
  "blob.drained",
  "blob.drain_skipped",
  "blob.promoted",
  "blob.promotion_failed",
  "blob.promotion_skipped",
  "blob.purged",
  "blob.purge_failed",
  "filesystem_event.trimmed",
  "folder.access.granted",
  "folder.access.revoked",
  "folder.access.updated",
  "folder.deleted",
  "folder.duplicated",
  "folder.preferred_storage_backend.updated",
  "multipart_upload.aborted",
  "storage_backend.created",
  "storage_backend.deleted",
  "storage_backend.drain_started",
  "storage_backend.drained",
  "storage_backend.probe_failed",
  "storage_backend.updated",
  "storage_backend_probe.trimmed",
  "user.created",
  "user.deleted",
  "user.updated",
] as const

export const AUDIT_STATUS_OPTIONS = [
  "succeeded",
  "failed",
  "skipped",
] as const satisfies readonly AuditEventStatus[]
