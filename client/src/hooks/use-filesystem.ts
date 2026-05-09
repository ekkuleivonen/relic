import { useQuery } from "@tanstack/react-query"

import { apiRequest } from "@/lib/api"
import type {
  FolderContentsSortDir,
  FolderContentsSortKey,
  FolderTreeNode,
  PaginatedFilesResponse,
} from "@/types/filesystem"

export const filesystemQueryKey = ["filesystem"] as const

export const FOLDER_FILES_PAGE_SIZE = 50

function folderSortToApi(key: FolderContentsSortKey): string {
  switch (key) {
    case "name":
      return "name"
    case "type":
      return "mimetype"
    case "size":
      return "size"
    case "updated":
      return "updated_at"
  }
}

export function useFolderTree() {
  return useQuery({
    queryKey: [...filesystemQueryKey, "tree"],
    queryFn: () => apiRequest<FolderTreeNode>("/folders/tree"),
  })
}

export function useFolderFiles(
  folderId: string | undefined,
  args: {
    offset: number
    sort: FolderContentsSortKey
    dir: FolderContentsSortDir
    limit?: number
  },
) {
  const limit = args.limit ?? FOLDER_FILES_PAGE_SIZE
  const sort = folderSortToApi(args.sort)
  return useQuery({
    queryKey: [
      ...filesystemQueryKey,
      "files",
      folderId,
      args.offset,
      limit,
      sort,
      args.dir,
    ],
    queryFn: () =>
      apiRequest<PaginatedFilesResponse>(
        `/files/?folder_id=${folderId}&limit=${limit}&offset=${args.offset}&sort=${sort}&order=${args.dir}`,
      ),
    enabled: folderId !== undefined,
  })
}
