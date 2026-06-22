import { useQuery } from "@tanstack/react-query"

import { apiRequest } from "@/lib/api"
import { serializeSearchQuery } from "@/lib/search-query"
import type { Facets, FileSearchResponse, SearchQuery } from "@/types/search"

export const searchQueryKey = ["search"] as const

function toApiSearchParams(query: SearchQuery): URLSearchParams {
  const params = serializeSearchQuery(query)
  if (query.uploaded_by) {
    params.delete("uploaded_by")
    params.set("actor_id", query.uploaded_by)
  }
  return params
}

export function useFileSearch(query: SearchQuery, options?: { enabled?: boolean }) {
  const params = toApiSearchParams(query).toString()
  return useQuery({
    queryKey: [...searchQueryKey, "files", params],
    queryFn: () =>
      apiRequest<FileSearchResponse>(
        params ? `/files/search?${params}` : "/files/search"
      ),
    placeholderData: (previous) => previous,
    enabled: options?.enabled ?? true,
  })
}

export function useSearchFacets(
  query: SearchQuery,
  options?: { enabled?: boolean; top?: number }
) {
  const params = toApiSearchParams(query)
  // Pagination params do not affect facets; strip them so the cache reuses
  // results across pagination changes.
  params.delete("limit")
  params.delete("offset")
  if (options?.top !== undefined) {
    params.set("top", String(options.top))
  }
  const queryString = params.toString()
  return useQuery({
    queryKey: [...searchQueryKey, "facets", queryString],
    queryFn: () =>
      apiRequest<Facets>(
        queryString ? `/files/facets?${queryString}` : "/files/facets"
      ),
    placeholderData: (previous) => previous,
    enabled: options?.enabled ?? true,
  })
}
