import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { objectKeys } from "@/features/objects/hooks/use-objects"
import { searchAttributesQueryKey } from "@/features/search/hooks/use-search-attributes"
import { apiRequest, extractApiError } from "@/lib/api"
import type { CatalogObject, PatchObjectAttributesInput } from "@/types/objects"

export function usePatchObjectAttributes(objectId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: PatchObjectAttributesInput) =>
      apiRequest<CatalogObject>(`/objects/${objectId}/attributes`, {
        method: "PATCH",
        body: input,
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: objectKeys.detail(objectId),
        }),
        queryClient.invalidateQueries({
          queryKey: searchAttributesQueryKey,
        }),
      ])
      toast.success("User attributes updated")
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}
