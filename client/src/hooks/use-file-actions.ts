import * as React from "react"

import { FileActionsContext } from "@/components/filesystem/file-actions-context"

export function useFileActions() {
  const ctx = React.useContext(FileActionsContext)
  if (!ctx) {
    throw new Error("useFileActions must be used inside FileActionsProvider")
  }
  return ctx
}
