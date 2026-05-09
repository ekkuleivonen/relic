import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { apiRequest, extractApiError } from "@/lib/api"
import type {
  Bucket,
  BucketCreateInput,
  BucketProbeResult,
  BucketUpdateInput,
} from "@/types/buckets"

export const bucketQueryKey = ["buckets"] as const

export function useBuckets() {
  return useQuery({
    queryKey: bucketQueryKey,
    queryFn: () => apiRequest<Bucket[]>("/buckets/"),
  })
}

export function useCreateBucket() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: BucketCreateInput) =>
      apiRequest<Bucket>("/buckets/", {
        method: "POST",
        body: input,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: bucketQueryKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useUpdateBucket() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      bucketId,
      input,
    }: {
      bucketId: string
      input: BucketUpdateInput
    }) =>
      apiRequest<Bucket>(`/buckets/${bucketId}`, {
        method: "PATCH",
        body: input,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: bucketQueryKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useDeleteBucket() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (bucketId: string) =>
      apiRequest<void>(`/buckets/${bucketId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: bucketQueryKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useProbeBucket() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (bucketId: string) =>
      apiRequest<BucketProbeResult>(`/buckets/${bucketId}/probe`, {
        method: "POST",
      }),
    onSuccess: (result) => {
      toast.success(
        result.reachable
          ? `${result.name} probe completed`
          : `${result.name} could not be reached`
      )
      void queryClient.invalidateQueries({ queryKey: bucketQueryKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}
