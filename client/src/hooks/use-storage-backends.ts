import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { apiRequest, extractApiError } from "@/lib/api"
import type {
  DrainStorageBackendResponse,
  StorageBackend,
  StorageBackendCreateInput,
  StorageBackendProbeResult,
  StorageBackendUpdateInput,
} from "@/types/storage-backends"

export const storageBackendQueryKey = ["storage-backends"] as const

export function useStorageBackends() {
  return useQuery({
    queryKey: storageBackendQueryKey,
    queryFn: () => apiRequest<StorageBackend[]>("/storage-backends/"),
  })
}

export function useCreateStorageBackend() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: StorageBackendCreateInput) =>
      apiRequest<StorageBackend>("/storage-backends/", {
        method: "POST",
        body: input,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: storageBackendQueryKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useUpdateStorageBackend() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      storageBackendId,
      input,
    }: {
      storageBackendId: string
      input: StorageBackendUpdateInput
    }) =>
      apiRequest<StorageBackend>(`/storage-backends/${storageBackendId}`, {
        method: "PATCH",
        body: input,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: storageBackendQueryKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useDeleteStorageBackend() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (storageBackendId: string) =>
      apiRequest<void>(`/storage-backends/${storageBackendId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: storageBackendQueryKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useProbeStorageBackend() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (storageBackendId: string) =>
      apiRequest<StorageBackendProbeResult>(
        `/storage-backends/${storageBackendId}/probe`,
        {
          method: "POST",
        }
      ),
    onSuccess: (result) => {
      toast.success(
        result.reachable
          ? `${result.name} probe completed`
          : `${result.name} could not be reached`
      )
      void queryClient.invalidateQueries({ queryKey: storageBackendQueryKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useDrainStorageBackend() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (storageBackendId: string) =>
      apiRequest<DrainStorageBackendResponse>(
        `/storage-backends/${storageBackendId}/drain`,
        {
          method: "POST",
        }
      ),
    onSuccess: (result) => {
      toast.success(
        `Drain complete: ${result.moved} moved, ${result.skipped} skipped, ${result.failed} failed`
      )
      void queryClient.invalidateQueries({ queryKey: storageBackendQueryKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}
