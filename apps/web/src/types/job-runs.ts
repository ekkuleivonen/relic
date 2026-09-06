export type JobRunState =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"

export type JobRunType =
  | "sync_bucket"
  | "scan_bucket"
  | "import_objects"
  | "remove_objects"
  | "refresh_objects"
  | "extract_attributes"
  | "detect_duplicates"
  | "cleanup_runs"

export type JobRunPayload = Record<string, unknown>

export type TraceBatchState = {
  total: number
  done: number
  failed: number
  active: number
  pending: number
}

export type TraceObjectCounts = {
  import: number
  refresh: number
  remove: number
}

export type TraceJobTypeCounts = {
  total: number
  pending: number
  running: number
  succeeded: number
  failed: number
  cancelled: number
}

export type TraceSummary = {
  trace_id: string
  root_job_run_id: string
  state: JobRunState
  phase: string
  objects_listed: number
  objects_planned: TraceObjectCounts
  objects_applied: TraceObjectCounts
  batches: {
    import: TraceBatchState
    refresh: TraceBatchState
    remove: TraceBatchState
  }
  stale_seconds: number
  job_counts: Partial<Record<JobRunType, TraceJobTypeCounts>>
}

export type JobRun = {
  id: string
  trace_id: string
  type: JobRunType
  state: JobRunState
  requested_by_type?: string
  requested_by_id?: string
  target_type?: string
  target_id?: string
  input: JobRunPayload
  result: JobRunPayload
  progress: JobRunPayload
  attempt: number
  max_attempts: number
  available_at: string
  locked_by?: string
  locked_at?: string
  started_at?: string
  finished_at?: string
  error_message?: string
  created_at: string
  updated_at: string
  trace_summary?: TraceSummary
}

export type ListJobRunsParams = {
  type?: JobRunType
  types?: JobRunType[]
  state?: JobRunState
  traceId?: string
  requestedByType?: string
  requestedById?: string
  targetType?: string
  targetId?: string
  createdAfter?: string
  createdBefore?: string
  limit?: number
  offset?: number
}

export type ListJobRunsResponse = {
  job_runs: JobRun[]
  total: number
  limit: number
  offset: number
}
