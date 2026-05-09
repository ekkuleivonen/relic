import { useQuery } from "@tanstack/react-query"

import { apiRequest } from "@/lib/api"
import type { FileSystemFile, FolderTreeNode } from "@/types/filesystem"

export const filesystemQueryKey = ["filesystem"] as const

export function useFolderTree() {
  return useQuery({
    queryKey: [...filesystemQueryKey, "tree"],
    queryFn: () => apiRequest<FolderTreeNode>("/folders/tree"),
  })
}

export function useFolderFiles(folderId: string | undefined) {
  return useQuery({
    queryKey: [...filesystemQueryKey, "files", folderId],
    queryFn: () => apiRequest<FileSystemFile[]>(`/files/?folder_id=${folderId}`),
    enabled: folderId !== undefined,
  })
}
