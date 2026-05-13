import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { apiRequest, extractApiError } from "@/lib/api"
import type { FileEventsQuery, FileEventsResponse } from "@/types/file-events"

export const FILE_EVENTS_PAGE_SIZE = 50

export const fileEventsQueryRootKey = ["file-events"] as const
export const fileEventsQueryKey = (query: FileEventsQuery) =>
  [...fileEventsQueryRootKey, query] as const

export function useFileEvents(query: FileEventsQuery) {
  return useQuery({
    queryKey: fileEventsQueryKey(query),
    queryFn: () =>
      apiRequest<FileEventsResponse>(`/file-events/${toQueryString(query)}`),
  })
}

export function useClearFileEvents() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () =>
      apiRequest<void>("/file-events/", {
        method: "DELETE",
      }),
    onSuccess: () => {
      toast.success("File event log cleared")
      void queryClient.invalidateQueries({ queryKey: fileEventsQueryRootKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

function toQueryString(query: FileEventsQuery) {
  const params = new URLSearchParams()
  addString(params, "event_type", query.event_type)
  addString(params, "status", query.status)
  addString(params, "actor_id", query.actor_id)
  addString(params, "request_id", query.request_id)
  addString(params, "file_id", query.file_id)
  addString(params, "folder_id", query.folder_id)
  addString(params, "created_after", query.created_after)
  addString(params, "created_before", query.created_before)
  params.set("limit", String(query.limit ?? FILE_EVENTS_PAGE_SIZE))
  params.set("offset", String(query.offset ?? 0))
  const serialized = params.toString()
  return serialized ? `?${serialized}` : ""
}

function addString(
  params: URLSearchParams,
  key: string,
  value: string | undefined
) {
  const cleaned = value?.trim()
  if (cleaned) {
    params.set(key, cleaned)
  }
}
