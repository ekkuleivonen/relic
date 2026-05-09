import * as React from "react"

import type { FileSystemFile, FolderTreeNode } from "@/types/filesystem"

export type FileActionsContextValue = {
  openRename: (file: FileSystemFile) => void
  openDuplicate: (file: FileSystemFile, folder: FolderTreeNode) => void
  openMove: (file: FileSystemFile, folder: FolderTreeNode) => void
  openDelete: (file: FileSystemFile) => void
  download: (file: FileSystemFile) => void
}

export const FileActionsContext =
  React.createContext<FileActionsContextValue | null>(null)
