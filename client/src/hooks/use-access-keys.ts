import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { apiRequest, extractApiError } from "@/lib/api"
import type {
  AccessKey,
  AccessKeyCreateInput,
  CreatedAccessKey,
} from "@/types/access-keys"

export const accessKeysQueryKey = ["access-keys"] as const

export function useAccessKeys() {
  return useQuery({
    queryKey: accessKeysQueryKey,
    queryFn: () => apiRequest<AccessKey[]>("/access-keys/"),
  })
}

export function useCreateAccessKey() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: AccessKeyCreateInput) =>
      apiRequest<CreatedAccessKey>("/access-keys/", {
        method: "POST",
        body: input,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: accessKeysQueryKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useRevokeAccessKey() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (keyId: string) =>
      apiRequest<AccessKey>(`/access-keys/${keyId}/revoke`, {
        method: "POST",
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: accessKeysQueryKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}
