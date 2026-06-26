import { useQuery } from "@tanstack/react-query"

import { apiRequest } from "@/lib/api"
import type { ListSearchAttributesResponse } from "@/types/search"

export const searchAttributesQueryKey = ["search", "attributes"] as const

export function useSearchAttributes() {
  return useQuery({
    queryKey: searchAttributesQueryKey,
    queryFn: () =>
      apiRequest<ListSearchAttributesResponse>("/search/attributes"),
  })
}
