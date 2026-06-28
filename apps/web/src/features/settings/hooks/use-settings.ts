import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { apiRequest, extractApiError } from "@/lib/api"
import type {
  Setting,
  SettingPatchInput,
  SettingsListResponse,
} from "@/types/settings"

export const settingsKeys = {
  all: ["settings"] as const,
}

export function useSettings() {
  return useQuery({
    queryKey: settingsKeys.all,
    queryFn: async () => {
      const response = await apiRequest<SettingsListResponse>("/settings")
      return response.items
    },
  })
}

export function usePatchSetting() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ key, input }: { key: string; input: SettingPatchInput }) =>
      apiRequest<Setting>(`/settings/${encodeURIComponent(key)}`, {
        method: "PATCH",
        body: input,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: settingsKeys.all })
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}

export function usePatchSettings() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (updates: Record<string, string>) => {
      await Promise.all(
        Object.entries(updates).map(([key, value]) =>
          apiRequest<Setting>(`/settings/${encodeURIComponent(key)}`, {
            method: "PATCH",
            body: { value },
          }),
        ),
      )
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: settingsKeys.all })
      toast.success("Settings saved")
    },
    onError: (error) => {
      toast.error(extractApiError(error))
    },
  })
}
