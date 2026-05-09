import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { apiRequest, extractApiError } from "@/lib/api"
import type { User, UserCreateInput, UserUpdateInput } from "@/types/users"

export const userQueryKey = ["users"] as const

export function useUsers() {
  return useQuery({
    queryKey: userQueryKey,
    queryFn: () => apiRequest<User[]>("/users/"),
  })
}

export function useCreateUser() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: UserCreateInput) =>
      apiRequest<User>("/users/", {
        method: "POST",
        body: input,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: userQueryKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useUpdateUser() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      userId,
      input,
    }: {
      userId: string
      input: UserUpdateInput
    }) =>
      apiRequest<User>(`/users/${userId}`, {
        method: "PATCH",
        body: input,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: userQueryKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function useDeleteUser() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (userId: string) =>
      apiRequest<void>(`/users/${userId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: userQueryKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}
