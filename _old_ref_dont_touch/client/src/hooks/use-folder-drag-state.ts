import * as React from "react"

import type { FolderTreeNode } from "@/types/filesystem"

export type FolderDragState = {
  activeFolder: FolderTreeNode | null
  /** Includes the active folder itself; used to forbid self/descendant drops. */
  invalidTargetIds: Set<string>
}

export const FolderDragStateContext = React.createContext<FolderDragState>({
  activeFolder: null,
  invalidTargetIds: new Set(),
})

export function useFolderDragState() {
  return React.useContext(FolderDragStateContext)
}
