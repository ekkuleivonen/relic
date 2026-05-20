import { useQuery } from "@tanstack/react-query"

import { apiRequest } from "@/lib/api"
import type {
  FilesystemEventsQuery,
  FilesystemEventsResponse,
} from "@/types/filesystem-events"

export const FILESYSTEM_EVENTS_PAGE_SIZE = 50

export const filesystemEventsQueryRootKey = ["filesystem-events"] as const
export const filesystemEventsQueryKey = (query: FilesystemEventsQuery) =>
  [...filesystemEventsQueryRootKey, query] as const

export function useFilesystemEvents(query: FilesystemEventsQuery) {
  return useQuery({
    queryKey: filesystemEventsQueryKey(query),
    queryFn: () =>
      apiRequest<FilesystemEventsResponse>(
        `/filesystem-events/${toQueryString(query)}`
      ),
  })
}

function toQueryString(query: FilesystemEventsQuery) {
  const params = new URLSearchParams()
  params.set("after", String(query.after ?? 0))
  params.set("limit", String(query.limit ?? FILESYSTEM_EVENTS_PAGE_SIZE))
  if (query.recursive) {
    params.set("recursive", "true")
  }
  addString(params, "folder_id", query.folder_id)
  for (const eventType of query.types ?? []) {
    params.append("types", eventType)
  }
  const serialized = params.toString()
  return serialized ? `?${serialized}` : ""
}

function addString(params: URLSearchParams, key: string, value: string | undefined) {
  const cleaned = value?.trim()
  if (cleaned) {
    params.set(key, cleaned)
  }
}
