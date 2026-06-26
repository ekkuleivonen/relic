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

export type JobRun = {
  id: string
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
}

export type ListJobRunsParams = {
  type?: JobRunType
  state?: JobRunState
  targetType?: string
  targetId?: string
  limit?: number
  offset?: number
}

export type ListJobRunsResponse = {
  job_runs: JobRun[]
}
