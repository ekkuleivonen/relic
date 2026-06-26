import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { apiRequest, extractApiError } from "@/lib/api"
import type {
  Bucket,
  CreateBucketInput,
  ListBucketsResponse,
  UpdateBucketInput,
} from "@/types/buckets"
import type { JobRun } from "@/types/jobs"

const bucketKeys = {
  all: ["buckets"] as const,
}

const jobRunKeys = {
  all: ["job-runs"] as const,
}

export function useBuckets() {
  return useQuery({
    queryKey: bucketKeys.all,
    queryFn: () => apiRequest<ListBucketsResponse>("/buckets"),
  })
}

export function useBucket(bucketId: string | undefined) {
  return useQuery({
    queryKey: [...bucketKeys.all, bucketId],
    queryFn: () => apiRequest<Bucket>(`/buckets/${bucketId}`),
    enabled: Boolean(bucketId),
  })
}

export function useCreateBucket() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: CreateBucketInput) =>
      apiRequest<Bucket>("/buckets", {
        method: "POST",
        body: input,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: bucketKeys.all })
      toast.success("Bucket connected")
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useUpdateBucket(bucketId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: UpdateBucketInput) =>
      apiRequest<Bucket>(`/buckets/${bucketId}`, {
        method: "PATCH",
        body: input,
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: bucketKeys.all }),
        queryClient.invalidateQueries({ queryKey: [...bucketKeys.all, bucketId] }),
      ])
      toast.success("Bucket updated")
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useSyncBucket(bucketId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () =>
      apiRequest<JobRun>(`/buckets/${bucketId}/sync`, {
        method: "POST",
      }),
    onSuccess: async (jobRun) => {
      await queryClient.invalidateQueries({ queryKey: jobRunKeys.all })
      toast.success(`Sync queued (${jobRun.id})`)
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}
