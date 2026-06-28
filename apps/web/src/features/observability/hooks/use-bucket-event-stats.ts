import { useQuery } from "@tanstack/react-query"

import { apiRequest } from "@/lib/api"
import type {
  ActivityStats,
  BucketEventStatsParams,
} from "@/types/observability-stats"

export const bucketEventStatsKeys = {
  all: ["bucket-events", "stats"] as const,
  detail: (params: BucketEventStatsParams) =>
    [...bucketEventStatsKeys.all, params] as const,
}

export function useBucketEventStats(
  params: BucketEventStatsParams,
  options: { enabled?: boolean; refetchInterval?: number | false } = {}
) {
  return useQuery({
    queryKey: bucketEventStatsKeys.detail(params),
    queryFn: () =>
      apiRequest<ActivityStats>(
        `/bucket-events/stats${bucketEventStatsQueryString(params)}`
      ),
    enabled: options.enabled ?? true,
    refetchInterval: options.refetchInterval,
  })
}

function bucketEventStatsQueryString(params: BucketEventStatsParams) {
  const searchParams = new URLSearchParams()

  appendParam(searchParams, "bucket_id", params.bucketId)
  appendParam(searchParams, "state", params.state)
  appendParam(searchParams, "received_after", params.receivedAfter)
  appendParam(searchParams, "received_before", params.receivedBefore)

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
