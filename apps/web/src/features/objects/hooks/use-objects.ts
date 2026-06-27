import { useQuery } from "@tanstack/react-query"

import { apiRequest } from "@/lib/api"
import type {
  CatalogObject,
  ListObjectsParams,
  ListObjectsResponse,
} from "@/types/objects"

const objectKeys = {
  all: ["objects"] as const,
  list: (params: ListObjectsParams) => [...objectKeys.all, params] as const,
  detail: (objectId: string | undefined) =>
    [...objectKeys.all, "detail", objectId] as const,
}

export function useObjects(
  params: ListObjectsParams,
  options?: { live?: boolean }
) {
  return useQuery({
    queryKey: objectKeys.list(params),
    queryFn: () =>
      apiRequest<ListObjectsResponse>(`/objects${objectQueryString(params)}`),
    refetchOnWindowFocus: true,
    refetchInterval: options?.live ? 5_000 : false,
  })
}

export function useObject(objectId: string | undefined) {
  return useQuery({
    queryKey: objectKeys.detail(objectId),
    queryFn: () => apiRequest<CatalogObject>(`/objects/${objectId}`),
    enabled: Boolean(objectId),
  })
}

function objectQueryString(params: ListObjectsParams) {
  const searchParams = new URLSearchParams()

  appendParam(searchParams, "bucket_id", params.bucketId)
  appendParam(searchParams, "prefix", params.prefix)
  appendParam(searchParams, "content_type", params.contentType)
  appendParam(searchParams, "key_contains", params.keyContains)
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
