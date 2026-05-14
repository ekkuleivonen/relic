import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { apiRequest, extractApiError } from "@/lib/api"
import type {
  Processor,
  ProcessorCreateInput,
  ProcessorFolderOptionsResponse,
  ProcessorKindsResponse,
  ProcessorListResponse,
  ProcessorRewindInput,
  ProcessorSkipInput,
  ProcessorUpdateInput,
} from "@/types/processors"

export const PROCESSORS_PAGE_SIZE = 50

export const processorsQueryRootKey = ["processors"] as const
export const processorsListQueryKey = (limit: number, offset: number) =>
  [...processorsQueryRootKey, "list", { limit, offset }] as const
export const processorKindsQueryKey = [
  ...processorsQueryRootKey,
  "kinds",
] as const
export const processorFolderOptionsQueryKey = [
  ...processorsQueryRootKey,
  "folder-options",
] as const

export function useProcessors(
  params: { limit?: number; offset?: number } = {}
) {
  const limit = params.limit ?? PROCESSORS_PAGE_SIZE
  const offset = params.offset ?? 0
  return useQuery({
    queryKey: processorsListQueryKey(limit, offset),
    queryFn: () =>
      apiRequest<ProcessorListResponse>(
        `/processors/?limit=${limit}&offset=${offset}`
      ),
  })
}

export function useProcessorKinds() {
  return useQuery({
    queryKey: processorKindsQueryKey,
    queryFn: () => apiRequest<ProcessorKindsResponse>("/processors/kinds"),
  })
}

export function useProcessorFolderOptions() {
  return useQuery({
    queryKey: processorFolderOptionsQueryKey,
    queryFn: () =>
      apiRequest<ProcessorFolderOptionsResponse>("/processors/folder-options"),
  })
}

function invalidateProcessors(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: processorsQueryRootKey })
}

export function useCreateProcessor() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: ProcessorCreateInput) =>
      apiRequest<Processor>("/processors/", {
        method: "POST",
        body: input,
      }),
    onSuccess: () => {
      toast.success("Processor created")
      invalidateProcessors(queryClient)
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useUpdateProcessor() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      processorId,
      input,
    }: {
      processorId: string
      input: ProcessorUpdateInput
    }) =>
      apiRequest<Processor>(`/processors/${processorId}`, {
        method: "PATCH",
        body: input,
      }),
    onSuccess: () => {
      invalidateProcessors(queryClient)
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useDeleteProcessor() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (processorId: string) =>
      apiRequest<void>(`/processors/${processorId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      toast.success("Processor deleted")
      invalidateProcessors(queryClient)
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useRewindProcessor() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      processorId,
      input,
    }: {
      processorId: string
      input: ProcessorRewindInput
    }) =>
      apiRequest<Processor>(`/processors/${processorId}/rewind`, {
        method: "POST",
        body: input,
      }),
    onSuccess: () => {
      toast.success("Processor cursor rewound")
      invalidateProcessors(queryClient)
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useSkipStuckEvent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      processorId,
      input,
    }: {
      processorId: string
      input: ProcessorSkipInput
    }) =>
      apiRequest<Processor>(`/processors/${processorId}/skip`, {
        method: "POST",
        body: input,
      }),
    onSuccess: () => {
      toast.success("Stuck event skipped")
      invalidateProcessors(queryClient)
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}
