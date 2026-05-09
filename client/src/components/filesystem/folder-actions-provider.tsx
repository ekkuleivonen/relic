import * as React from "react"

import {
  FolderActionsContext,
  type FolderActionsContextValue,
} from "@/components/filesystem/folder-actions-context"
import {
  CreateFolderDialog,
  DeleteFolderDialog,
  DuplicateFolderDialog,
  RenameFolderDialog,
} from "@/components/filesystem/folder-dialogs"
import type { FolderTreeNode } from "@/types/filesystem"

type DialogState =
  | { kind: "none" }
  | { kind: "create"; parent: FolderTreeNode }
  | { kind: "rename"; folder: FolderTreeNode }
  | { kind: "duplicate"; folder: FolderTreeNode }
  | { kind: "delete"; folder: FolderTreeNode; onDeleted?: () => void }

export function FolderActionsProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<DialogState>({ kind: "none" })

  const value = React.useMemo<FolderActionsContextValue>(
    () => ({
      openCreate: (parent) => setState({ kind: "create", parent }),
      openRename: (folder) => setState({ kind: "rename", folder }),
      openDuplicate: (folder) => setState({ kind: "duplicate", folder }),
      openDelete: (folder, onDeleted) =>
        setState({ kind: "delete", folder, onDeleted }),
    }),
    []
  )

  function close(open: boolean) {
    if (!open) {
      setState({ kind: "none" })
    }
  }

  return (
    <FolderActionsContext.Provider value={value}>
      {children}
      {state.kind === "create" && (
        <CreateFolderDialog
          open
          onOpenChange={close}
          parent={state.parent}
        />
      )}
      {state.kind === "rename" && (
        <RenameFolderDialog
          open
          onOpenChange={close}
          folder={state.folder}
        />
      )}
      {state.kind === "duplicate" && (
        <DuplicateFolderDialog
          open
          onOpenChange={close}
          folder={state.folder}
        />
      )}
      {state.kind === "delete" && (
        <DeleteFolderDialog
          open
          onOpenChange={close}
          folder={state.folder}
          onDeleted={state.onDeleted}
        />
      )}
    </FolderActionsContext.Provider>
  )
}
