import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { apiRequest, extractApiError } from "@/lib/api"
import type {
  Collection,
  CreateCollectionInput,
  ListCollectionObjectsResponse,
  ListCollectionsResponse,
  UpdateCollectionInput,
} from "@/types/collections"

const collectionKeys = {
  all: ["collections"] as const,
}

export function useCollections() {
  return useQuery({
    queryKey: collectionKeys.all,
    queryFn: () => apiRequest<ListCollectionsResponse>("/collections"),
  })
}

export function useCollection(collectionId: string | undefined) {
  return useQuery({
    queryKey: [...collectionKeys.all, collectionId],
    queryFn: () => apiRequest<Collection>(`/collections/${collectionId}`),
    enabled: Boolean(collectionId),
  })
}

export function useCollectionObjects(collectionId: string | undefined) {
  return useQuery({
    queryKey: [...collectionKeys.all, collectionId, "objects"],
    queryFn: () =>
      apiRequest<ListCollectionObjectsResponse>(
        `/collections/${collectionId}/objects`
      ),
    enabled: Boolean(collectionId),
  })
}

export function useCreateCollection() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: CreateCollectionInput) =>
      apiRequest<Collection>("/collections", {
        method: "POST",
        body: input,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: collectionKeys.all })
      toast.success("Collection created")
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useUpdateCollection(collectionId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: UpdateCollectionInput) =>
      apiRequest<Collection>(`/collections/${collectionId}`, {
        method: "PATCH",
        body: input,
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: collectionKeys.all }),
        queryClient.invalidateQueries({
          queryKey: [...collectionKeys.all, collectionId],
        }),
        queryClient.invalidateQueries({
          queryKey: [...collectionKeys.all, collectionId, "objects"],
        }),
      ])
      toast.success("Collection updated")
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useDeleteCollection(collectionId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () =>
      apiRequest<void>(`/collections/${collectionId}`, {
        method: "DELETE",
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: collectionKeys.all })
      toast.success("Collection deleted")
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}
