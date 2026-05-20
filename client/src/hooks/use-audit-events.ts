import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { apiRequest, extractApiError } from "@/lib/api"
import type {
  AuditEventsQuery,
  AuditEventsResponse,
} from "@/types/audit-events"

export const AUDIT_EVENTS_PAGE_SIZE = 50

export const auditEventsQueryRootKey = ["audit-events"] as const
export const auditEventsQueryKey = (query: AuditEventsQuery) =>
  [...auditEventsQueryRootKey, query] as const

export function useAuditEvents(query: AuditEventsQuery) {
  return useQuery({
    queryKey: auditEventsQueryKey(query),
    queryFn: () =>
      apiRequest<AuditEventsResponse>(`/audit-events/${toQueryString(query)}`),
  })
}

export function useClearAuditEvents() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () =>
      apiRequest<void>("/audit-events/", {
        method: "DELETE",
      }),
    onSuccess: () => {
      toast.success("Audit log cleared")
      void queryClient.invalidateQueries({ queryKey: auditEventsQueryRootKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

function toQueryString(query: AuditEventsQuery) {
  const params = new URLSearchParams()
  addString(params, "operation", query.operation)
  addString(params, "status", query.status)
  addString(params, "actor_id", query.actor_id)
  addString(params, "request_id", query.request_id)
  addString(params, "job", query.job)
  addString(params, "batch_id", query.batch_id)
  addString(params, "bucket_id", query.bucket_id)
  addString(params, "blob_id", query.blob_id)
  addString(params, "created_after", query.created_after)
  addString(params, "created_before", query.created_before)
  params.set("limit", String(query.limit ?? AUDIT_EVENTS_PAGE_SIZE))
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
