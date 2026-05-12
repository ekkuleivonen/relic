import { useQuery } from "@tanstack/react-query"

import { apiRequest } from "@/lib/api"
import type { EventsQuery, EventsResponse } from "@/types/events"

export const EVENTS_PAGE_SIZE = 50

export const eventsQueryKey = (query: EventsQuery) => ["events", query] as const

export function useEvents(query: EventsQuery) {
  return useQuery({
    queryKey: eventsQueryKey(query),
    queryFn: () => apiRequest<EventsResponse>(`/events/${toQueryString(query)}`),
  })
}

function toQueryString(query: EventsQuery) {
  const params = new URLSearchParams()
  addString(params, "source", query.source)
  addString(params, "operation", query.operation)
  addString(params, "status", query.status)
  addString(params, "actor_user_id", query.actor_user_id)
  addString(params, "request_id", query.request_id)
  addString(params, "created_after", query.created_after)
  addString(params, "created_before", query.created_before)
  params.set("limit", String(query.limit ?? EVENTS_PAGE_SIZE))
  params.set("offset", String(query.offset ?? 0))
  const serialized = params.toString()
  return serialized ? `?${serialized}` : ""
}

function addString(params: URLSearchParams, key: string, value: string | undefined) {
  const cleaned = value?.trim()
  if (cleaned) {
    params.set(key, cleaned)
  }
}
