import { useQuery } from "@tanstack/react-query"

import { apiRequest } from "@/lib/api"
import type {
  JobRun,
  ListJobRunsParams,
  ListJobRunsResponse,
} from "@/types/job-runs"

export const jobRunKeys = {
  all: ["job-runs"] as const,
  list: (params: ListJobRunsParams) => [...jobRunKeys.all, params] as const,
  detail: (jobRunId: string | undefined) =>
    [...jobRunKeys.all, jobRunId] as const,
}

export function useJobRuns(
  params: ListJobRunsParams = {},
  options: { enabled?: boolean } = {}
) {
  return useQuery({
    queryKey: jobRunKeys.list(params),
    queryFn: () =>
      apiRequest<ListJobRunsResponse>(`/job-runs${jobRunQueryString(params)}`),
    enabled: options.enabled ?? true,
    refetchInterval: (query) =>
      hasActiveJobRuns(query.state.data?.job_runs) ? 3000 : false,
  })
}

export function useJobRun(jobRunId: string | undefined) {
  return useQuery({
    queryKey: jobRunKeys.detail(jobRunId),
    queryFn: () => apiRequest<JobRun>(`/job-runs/${jobRunId}`),
    enabled: Boolean(jobRunId),
    refetchInterval: (query) =>
      isActiveJobRun(query.state.data) ? 3000 : false,
  })
}

function jobRunQueryString(params: ListJobRunsParams) {
  const searchParams = new URLSearchParams()

  appendParam(searchParams, "type", params.type)
  appendParam(searchParams, "state", params.state)
  appendParam(searchParams, "requested_by_type", params.requestedByType)
  appendParam(searchParams, "requested_by_id", params.requestedById)
  appendParam(searchParams, "target_type", params.targetType)
  appendParam(searchParams, "target_id", params.targetId)
  appendParam(searchParams, "limit", params.limit?.toString())
  appendParam(searchParams, "offset", params.offset?.toString())

  const query = searchParams.toString()
  return query ? `?${query}` : ""
}

function appendParam(
  searchParams: URLSearchParams,
  key: string,
  value: string | undefined
) {
  if (value) {
    searchParams.set(key, value)
  }
}

function hasActiveJobRuns(jobRuns: JobRun[] | undefined) {
  return jobRuns?.some(isActiveJobRun) ?? false
}

function isActiveJobRun(jobRun: JobRun | undefined) {
  return jobRun?.state === "pending" || jobRun?.state === "running"
}
