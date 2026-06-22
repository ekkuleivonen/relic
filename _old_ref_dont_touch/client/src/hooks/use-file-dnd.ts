import type { FolderTreeNode } from "@/types/filesystem"

export const DRAG_TYPE_FILE = "file" as const

export type FileDragData = {
  type: typeof DRAG_TYPE_FILE
  file: {
    id: string
    folder_id: string
    name: string
  }
}

export function isFileMoveAllowed(
  source: FileDragData["file"],
  destination: FolderTreeNode
): boolean {
  if (source.folder_id === destination.id) return false
  return true
}
