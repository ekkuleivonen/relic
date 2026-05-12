import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { filesystemQueryKey } from "@/hooks/use-filesystem"
import { apiRequest, extractApiError } from "@/lib/api"
import type { Folder } from "@/types/filesystem"

type CreateFolderInput = {
  parent_id: string
  name: string
}

type UpdateFolderInput = {
  id: string
  name?: string
  parent_id?: string
  min_tier?: number | null
  cooldown_days?: number | null
}

type DeleteFolderInput = {
  id: string
  recursive?: boolean
}

type DuplicateFolderInput = {
  id: string
  destination_parent_id: string
  name: string
  recursive?: boolean
}

function invalidateAll(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: filesystemQueryKey })
}

export function useCreateFolder() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ parent_id, name }: CreateFolderInput) =>
      apiRequest<Folder>("/folders/", {
        method: "POST",
        body: { parent_id, name },
      }),
    onSuccess: (folder) => {
      invalidateAll(queryClient)
      toast.success(`Created '${folder.name}'`)
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useUpdateFolder() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, ...rest }: UpdateFolderInput) => {
      const body: Record<string, unknown> = {}
      if (rest.name !== undefined) {
        body.name = rest.name
      }
      if (rest.parent_id !== undefined) {
        body.parent_id = rest.parent_id
      }
      if (rest.min_tier !== undefined) {
        body.min_tier = rest.min_tier
      }
      if (rest.cooldown_days !== undefined) {
        body.cooldown_days = rest.cooldown_days
      }
      return apiRequest<Folder>(`/folders/${id}`, {
        method: "PATCH",
        body,
      })
    },
    onSuccess: () => {
      invalidateAll(queryClient)
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useDeleteFolder() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, recursive }: DeleteFolderInput) =>
      apiRequest<void>(
        `/folders/${id}${recursive ? "?recursive=true" : ""}`,
        { method: "DELETE" }
      ),
    onSuccess: () => {
      invalidateAll(queryClient)
      toast.success("Folder deleted")
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useDuplicateFolder() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      id,
      destination_parent_id,
      name,
      recursive = true,
    }: DuplicateFolderInput) =>
      apiRequest<Folder>(`/folders/${id}/copy`, {
        method: "POST",
        body: { destination_parent_id, name, recursive },
      }),
    onSuccess: (folder) => {
      invalidateAll(queryClient)
      toast.success(`Duplicated to '${folder.name}'`)
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}
