import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { filesystemQueryKey } from "@/hooks/use-filesystem"
import { ApiError, apiRequest, extractApiError, resolveServerUrl } from "@/lib/api"
import type {
  FileSystemFile,
  PresignUploadResponse,
} from "@/types/filesystem"

type DeleteFileInput = {
  file_id: string
  filename?: string
}

type DownloadFileInput = {
  file_id: string
  filename: string
}

type CopyFileInput = {
  source_file_id: string
  destination_folder_id: string
  name?: string | null
  metadata_directive?: "COPY" | "REPLACE"
  meta?: Record<string, string>
}

type MoveFileInput = {
  file_id: string
  destination_folder_id: string
  name?: string | null
}

type RenameFileInput = {
  file_id: string
  name: string
}

function invalidateAll(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: filesystemQueryKey })
}

export function useFile(fileId: string | undefined) {
  return useQuery({
    queryKey: [...filesystemQueryKey, "file", fileId],
    queryFn: () => apiRequest<FileSystemFile>(`/files/${fileId}`),
    enabled: fileId !== undefined,
  })
}

export function useDeleteFile() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ file_id }: DeleteFileInput) => {
      const signed = await apiRequest<PresignUploadResponse>(
        "/uploads/presign-delete",
        { method: "POST", body: { file_id } }
      )
      const response = await fetch(resolveServerUrl(signed.url), {
        method: "DELETE",
        headers: signed.headers,
      })
      if (!response.ok) {
        throw await buildGatewayError(response)
      }
    },
    onSuccess: (_result, { filename }) => {
      invalidateAll(queryClient)
      toast.success(filename ? `Deleted '${filename}'` : "File deleted")
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useDownloadFile() {
  return useMutation({
    mutationFn: async ({ file_id, filename }: DownloadFileInput) => {
      const signed = await apiRequest<PresignUploadResponse>(
        "/uploads/presign-download",
        { method: "POST", body: { file_id } }
      )
      const response = await fetch(resolveServerUrl(signed.url), {
        headers: signed.headers,
      })
      if (!response.ok) {
        throw await buildGatewayError(response)
      }

      const url = URL.createObjectURL(await response.blob())
      triggerBrowserDownload(url, filename)
      window.setTimeout(() => URL.revokeObjectURL(url), 0)
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useCopyFile() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      source_file_id,
      destination_folder_id,
      name,
      metadata_directive = "COPY",
      meta = {},
    }: CopyFileInput) => {
      const body = {
        source_file_id,
        destination_folder_id,
        ...(name ? { name } : {}),
        metadata_directive,
        meta,
      }
      const signed = await apiRequest<PresignUploadResponse>(
        "/uploads/presign-copy",
        { method: "POST", body }
      )
      const response = await fetch(resolveServerUrl(signed.url), {
        method: "PUT",
        headers: signed.headers,
      })
      if (!response.ok) {
        throw await buildGatewayError(response)
      }
    },
    onSuccess: (_result, variables) => {
      invalidateAll(queryClient)
      toast.success(
        variables.name ? `Copied to '${variables.name}'` : "File copied"
      )
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useMoveFile() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ file_id, destination_folder_id, name }: MoveFileInput) =>
      apiRequest<FileSystemFile>(`/files/${file_id}/move`, {
        method: "POST",
        body: {
          destination_folder_id,
          ...(name ? { name } : {}),
        },
      }),
    onSuccess: () => {
      invalidateAll(queryClient)
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function usePatchFileMeta() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      file_id,
      meta,
    }: {
      file_id: string
      meta: Record<string, unknown>
    }) =>
      apiRequest<FileSystemFile>(`/files/${file_id}/meta`, {
        method: "PATCH",
        body: { meta },
      }),
    onSuccess: (file) => {
      invalidateAll(queryClient)
      void queryClient.setQueryData(
        [...filesystemQueryKey, "file", file.id],
        file
      )
      toast.success("Metadata updated")
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useRenameFile() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ file_id, name }: RenameFileInput) =>
      apiRequest<FileSystemFile>(`/files/${file_id}`, {
        method: "PATCH",
        body: { name },
      }),
    onSuccess: () => {
      invalidateAll(queryClient)
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

async function buildGatewayError(response: Response) {
  const body = await response.text()
  const message =
    extractXmlErrorMessage(body) ?? `Request failed with status ${response.status}`
  return new ApiError(message, response.status, { message })
}

function extractXmlErrorMessage(body: string) {
  const code = body.match(/<Code>(.*?)<\/Code>/)?.[1]
  const message = body.match(/<Message>(.*?)<\/Message>/)?.[1]

  if (code && message) {
    return `${code}: ${message}`
  }

  return message ?? code
}

function triggerBrowserDownload(url: string, filename: string) {
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  anchor.rel = "noopener"
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}
