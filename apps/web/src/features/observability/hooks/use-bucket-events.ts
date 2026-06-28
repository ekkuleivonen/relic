import { useQuery } from "@tanstack/react-query"

import { apiRequest } from "@/lib/api"
import type {
  BucketEvent,
  ListBucketEventsParams,
  ListBucketEventsResponse,
} from "@/types/bucket-events"

export const bucketEventKeys = {
  all: ["bucket-events"] as const,
  list: (params: ListBucketEventsParams) =>
    [...bucketEventKeys.all, params] as const,
  detail: (eventId: string | undefined) =>
    [...bucketEventKeys.all, eventId] as const,
}

export function useBucketEvents(
  params: ListBucketEventsParams = {},
  options: { refetchInterval?: number | false } = {}
) {
  return useQuery({
    queryKey: bucketEventKeys.list(params),
    queryFn: () =>
      apiRequest<ListBucketEventsResponse>(
        `/bucket-events${bucketEventQueryString(params)}`
      ),
    refetchInterval:
      options.refetchInterval ??
      ((query) =>
        hasPendingEvents(query.state.data?.bucket_events) ? 3000 : false),
  })
}

export function useBucketEvent(eventId: string | undefined) {
  return useQuery({
    queryKey: bucketEventKeys.detail(eventId),
    queryFn: () => apiRequest<BucketEvent>(`/bucket-events/${eventId}`),
    enabled: Boolean(eventId),
    refetchInterval: (query) =>
      query.state.data?.state === "pending" ? 3000 : false,
  })
}

function bucketEventQueryString(params: ListBucketEventsParams) {
  const searchParams = new URLSearchParams()

  appendParam(searchParams, "bucket_id", params.bucketId)
  appendParam(searchParams, "state", params.state)
  appendParam(searchParams, "category", params.category)
  appendParam(searchParams, "received_after", params.receivedAfter)
  appendParam(searchParams, "received_before", params.receivedBefore)
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

function hasPendingEvents(events: BucketEvent[] | undefined) {
  return events?.some((event) => event.state === "pending") ?? false
}
