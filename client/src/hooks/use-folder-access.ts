import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { apiRequest, extractApiError } from "@/lib/api"
import type {
  FolderAccess,
  FolderAccessGrantInput,
} from "@/types/folder-access"

export const folderAccessQueryKey = ["folder-access"] as const

export function useFolderAccess() {
  return useQuery({
    queryKey: folderAccessQueryKey,
    queryFn: () => apiRequest<FolderAccess[]>("/folder-access/"),
  })
}

export function useGrantFolderAccess() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: FolderAccessGrantInput) =>
      apiRequest<FolderAccess>("/folder-access/", {
        method: "POST",
        body: input,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: folderAccessQueryKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useRevokeFolderAccess() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (accessId: string) =>
      apiRequest<void>(`/folder-access/${accessId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: folderAccessQueryKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}
