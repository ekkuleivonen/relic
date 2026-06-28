import { useQuery } from "@tanstack/react-query"

import { apiRequest } from "@/lib/api"
import type { ActivityStats, JobRunStatsParams } from "@/types/observability-stats"

export const jobRunStatsKeys = {
  all: ["job-runs", "stats"] as const,
  detail: (params: JobRunStatsParams) => [...jobRunStatsKeys.all, params] as const,
}

export function useJobRunStats(
  params: JobRunStatsParams,
  options: { enabled?: boolean; refetchInterval?: number | false } = {}
) {
  return useQuery({
    queryKey: jobRunStatsKeys.detail(params),
    queryFn: () =>
      apiRequest<ActivityStats>(`/job-runs/stats${jobRunStatsQueryString(params)}`),
    enabled: options.enabled ?? true,
    refetchInterval: options.refetchInterval,
  })
}

function jobRunStatsQueryString(params: JobRunStatsParams) {
  const searchParams = new URLSearchParams()

  appendParam(searchParams, "type", params.type)
  appendParam(searchParams, "types", params.types?.join(","))
  appendParam(searchParams, "state", params.state)
  appendParam(searchParams, "requested_by_type", params.requestedByType)
  appendParam(searchParams, "requested_by_id", params.requestedById)
  appendParam(searchParams, "target_type", params.targetType)
  appendParam(searchParams, "target_id", params.targetId)
  appendParam(searchParams, "created_after", params.createdAfter)
  appendParam(searchParams, "created_before", params.createdBefore)

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
