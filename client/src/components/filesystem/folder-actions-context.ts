import * as React from "react"

import type { FolderTreeNode } from "@/types/filesystem"

export type FolderActionsContextValue = {
  openCreate: (parent: FolderTreeNode) => void
  openRename: (folder: FolderTreeNode) => void
  openDuplicate: (folder: FolderTreeNode) => void
  openDelete: (folder: FolderTreeNode, onDeleted?: () => void) => void
  openPreferredBucket: (folder: FolderTreeNode) => void
}

export const FolderActionsContext =
  React.createContext<FolderActionsContextValue | null>(null)
