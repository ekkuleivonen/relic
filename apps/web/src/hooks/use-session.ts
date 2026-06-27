import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { apiRequest, ApiError, extractApiError } from "@/lib/api"
import type { LoginInput, Session } from "@/types/auth"

export const sessionQueryKey = ["auth", "session"] as const

export function useSession() {
  return useQuery({
    queryKey: sessionQueryKey,
    queryFn: async () => {
      try {
        return await apiRequest<Session>("/auth/session")
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          return null
        }

        throw error
      }
    },
    retry: false,
  })
}

export function useLogin() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: LoginInput) =>
      apiRequest<Session>("/auth/login", {
        method: "POST",
        body: input,
      }),
    onSuccess: (session) => {
      queryClient.setQueryData(sessionQueryKey, session)
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useLogout() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () =>
      apiRequest<void>("/auth/logout", {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.setQueryData(sessionQueryKey, null)
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useSetPassword() {
  return useMutation({
    mutationFn: (password: string) =>
      apiRequest<void>("/auth/password", {
        method: "PATCH",
        body: { password },
      }),
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}
