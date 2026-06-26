import { useQuery } from "@tanstack/react-query"

import { apiRequest } from "@/lib/api"
import type { ExecuteSearchResponse } from "@/types/search"

export const searchExecuteQueryKey = (query: string, bucketId?: string) =>
  ["search", "execute", query, bucketId ?? ""] as const

type UseSearchExecuteOptions = {
  query: string
  bucketId?: string
  enabled: boolean
}

export function useSearchExecute({
  query,
  bucketId,
  enabled,
}: UseSearchExecuteOptions) {
  return useQuery({
    queryKey: searchExecuteQueryKey(query, bucketId),
    queryFn: () =>
      apiRequest<ExecuteSearchResponse>("/search", {
        method: "POST",
        body: {
          query,
          ...(bucketId ? { bucket_id: bucketId } : {}),
        },
      }),
    enabled: enabled && query.trim().length > 0,
    retry: false,
  })
}
