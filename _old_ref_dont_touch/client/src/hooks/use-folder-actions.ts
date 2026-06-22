import * as React from "react"

import { FolderActionsContext } from "@/components/filesystem/folder-actions-context"

export function useFolderActions() {
  const ctx = React.useContext(FolderActionsContext)
  if (!ctx) {
    throw new Error("useFolderActions must be used inside FolderActionsProvider")
  }
  return ctx
}
