import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"

import { apiRequest, extractApiError } from "@/lib/api"
import type { BlobGcResponse } from "@/types/blobs"

export function useBlobGc() {
  return useMutation({
    mutationFn: () =>
      apiRequest<BlobGcResponse>("/blobs/gc", {
        method: "POST",
      }),
    onSuccess: (result) => {
      toast.success(
        `GC complete: ${result.deleted_rows} blob(s) purged, ${result.errors} error(s)`
      )
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}
