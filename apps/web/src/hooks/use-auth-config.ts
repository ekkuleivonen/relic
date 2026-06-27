import { useQuery } from "@tanstack/react-query"

import { apiRequest } from "@/lib/api"
import type { AuthConfig } from "@/types/auth"

export const authConfigQueryKey = ["auth", "config"] as const

export function useAuthConfig() {
  return useQuery({
    queryKey: authConfigQueryKey,
    queryFn: () => apiRequest<AuthConfig>("/auth/config"),
    staleTime: 60_000,
  })
}
