import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { apiRequest, extractApiError } from "@/lib/api"
import type { User, UserCreateInput, UserUpdateInput } from "@/types/auth"

export const usersQueryKey = ["users"] as const

type UsersListResponse = {
  items: User[]
}

export function useUsers(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: usersQueryKey,
    queryFn: async () => {
      const response = await apiRequest<UsersListResponse>("/users")
      return response.items
    },
    enabled: options?.enabled ?? true,
  })
}

export function useCreateUser() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: UserCreateInput) =>
      apiRequest<User>("/users", {
        method: "POST",
        body: input,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: usersQueryKey })
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
      void queryClient.invalidateQueries({ queryKey: usersQueryKey })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}
