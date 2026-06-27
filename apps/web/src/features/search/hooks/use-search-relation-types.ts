import { useQuery } from "@tanstack/react-query"

import { apiRequest } from "@/lib/api"
import type { ListSearchRelationTypesResponse } from "@/types/search"

export const searchRelationTypesQueryKey = ["search", "relation-types"] as const

export function useSearchRelationTypes() {
  return useQuery({
    queryKey: searchRelationTypesQueryKey,
    queryFn: () =>
      apiRequest<ListSearchRelationTypesResponse>("/search/relation-types"),
  })
}
