import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { filesystemQueryKey } from "@/hooks/use-filesystem"
import { ApiError, apiRequest, extractApiError, resolveServerUrl } from "@/lib/api"
import type {
  PresignUploadRequest,
  PresignUploadResponse,
} from "@/types/filesystem"

type UploadFileInput = {
  folder_id: string
  file: File
  meta?: Record<string, string>
}

export function useFileUpload() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: uploadFile,
    onSuccess: (_result, { file }) => {
      void queryClient.invalidateQueries({ queryKey: filesystemQueryKey })
      toast.success(`Uploaded '${file.name}'`)
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

async function uploadFile({ folder_id, file, meta = {} }: UploadFileInput) {
  const presignPayload: PresignUploadRequest = {
    folder_id,
    filename: file.name,
    meta,
  }
  const signed = await apiRequest<PresignUploadResponse>("/uploads/presign", {
    method: "POST",
    body: presignPayload,
  })
  const response = await fetch(resolveServerUrl(signed.url), {
    method: "PUT",
    headers: signed.headers,
    body: file,
  })

  if (!response.ok) {
    throw await buildGatewayError(response)
  }
}

async function buildGatewayError(response: Response) {
  const body = await response.text()
  const message = extractXmlErrorMessage(body) ?? `Upload failed with status ${response.status}`
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
