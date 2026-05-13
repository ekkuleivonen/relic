import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { apiRequest, extractApiError } from "@/lib/api"
import type {
  MaintenanceEventsQuery,
  MaintenanceEventsResponse,
} from "@/types/maintenance-events"

export const MAINTENANCE_EVENTS_PAGE_SIZE = 50

export const maintenanceEventsQueryRootKey = ["maintenance-events"] as const
export const maintenanceEventsQueryKey = (query: MaintenanceEventsQuery) =>
  [...maintenanceEventsQueryRootKey, query] as const

export function useMaintenanceEvents(query: MaintenanceEventsQuery) {
  return useQuery({
    queryKey: maintenanceEventsQueryKey(query),
    queryFn: () =>
      apiRequest<MaintenanceEventsResponse>(
        `/maintenance-events/${toQueryString(query)}`
      ),
  })
}

export function useClearMaintenanceEvents() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () =>
      apiRequest<void>("/maintenance-events/", {
        method: "DELETE",
      }),
    onSuccess: () => {
      toast.success("Maintenance event log cleared")
      void queryClient.invalidateQueries({
        queryKey: maintenanceEventsQueryRootKey,
      })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

function toQueryString(query: MaintenanceEventsQuery) {
  const params = new URLSearchParams()
  addString(params, "job", query.job)
  addString(params, "action", query.action)
  addString(params, "status", query.status)
  addString(params, "batch_id", query.batch_id)
  addString(params, "bucket_id", query.bucket_id)
  addString(params, "blob_id", query.blob_id)
  addString(params, "created_after", query.created_after)
  addString(params, "created_before", query.created_before)
  params.set("limit", String(query.limit ?? MAINTENANCE_EVENTS_PAGE_SIZE))
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
