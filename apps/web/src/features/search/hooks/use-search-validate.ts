import { useMutation } from "@tanstack/react-query"

import { apiRequest } from "@/lib/api"
import type { ValidateSearchResponse } from "@/types/search"

export function useValidateSearch() {
  return useMutation({
    mutationFn: (query: string) =>
      apiRequest<ValidateSearchResponse>("/search/validate", {
        method: "POST",
        body: { query },
      }),
  })
}
