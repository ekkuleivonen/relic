import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { apiRequest, extractApiError } from "@/lib/api"
import type {
  CreateUpstreamCaptureFieldInput,
  UpdateUpstreamCaptureFieldInput,
  UpstreamCaptureField,
} from "@/types/upstream-capture"

export const captureFieldKeys = {
  all: ["upstream-capture-fields"] as const,
}

export function useUpstreamCaptureFields() {
  return useQuery({
    queryKey: captureFieldKeys.all,
    queryFn: () => apiRequest<UpstreamCaptureField[]>("/upstream-capture-fields"),
  })
}

export function useCreateUpstreamCaptureField() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: CreateUpstreamCaptureFieldInput) =>
      apiRequest<UpstreamCaptureField>("/upstream-capture-fields", {
        method: "POST",
        body: input,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: captureFieldKeys.all })
      toast.success("Capture field added")
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useUpdateUpstreamCaptureField() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      id,
      input,
    }: {
      id: string
      input: UpdateUpstreamCaptureFieldInput
    }) =>
      apiRequest<UpstreamCaptureField>(`/upstream-capture-fields/${id}`, {
        method: "PATCH",
        body: input,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: captureFieldKeys.all })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useDeleteUpstreamCaptureField() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) =>
      apiRequest<void>(`/upstream-capture-fields/${id}`, {
        method: "DELETE",
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: captureFieldKeys.all })
      toast.success("Capture field removed")
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}
