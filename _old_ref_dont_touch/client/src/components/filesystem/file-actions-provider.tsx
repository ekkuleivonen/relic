import * as React from "react"

import {
  FileActionsContext,
  type FileActionsContextValue,
} from "@/components/filesystem/file-actions-context"
import {
  DeleteFileAlertDialog,
  DuplicateFileDialog,
  MoveFileDialog,
  RenameFileDialog,
} from "@/components/filesystem/file-dialogs"
import { useDownloadFile } from "@/hooks/use-files"
import type { FileSystemFile, FolderTreeNode } from "@/types/filesystem"

type DialogState =
  | { kind: "none" }
  | { kind: "rename"; file: FileSystemFile }
  | { kind: "duplicate"; file: FileSystemFile; folder: FolderTreeNode }
  | { kind: "move"; file: FileSystemFile; folder: FolderTreeNode }
  | { kind: "delete"; file: FileSystemFile }

export function FileActionsProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<DialogState>({ kind: "none" })
  const download = useDownloadFile()

  const value = React.useMemo<FileActionsContextValue>(
    () => ({
      openRename: (file) => setState({ kind: "rename", file }),
      openDuplicate: (file, folder) =>
        setState({ kind: "duplicate", file, folder }),
      openMove: (file, folder) => setState({ kind: "move", file, folder }),
      openDelete: (file) => setState({ kind: "delete", file }),
      download: (file) => {
        download.mutate({ file_id: file.id, filename: file.name })
      },
    }),
    [download]
  )

  function close(open: boolean) {
    if (!open) {
      setState({ kind: "none" })
    }
  }

  return (
    <FileActionsContext.Provider value={value}>
      {children}
      {state.kind === "rename" && (
        <RenameFileDialog open onOpenChange={close} file={state.file} />
      )}
      {state.kind === "duplicate" && (
        <DuplicateFileDialog
          open
          onOpenChange={close}
          file={state.file}
          folder={state.folder}
        />
      )}
      {state.kind === "move" && (
        <MoveFileDialog
          open
          onOpenChange={close}
          file={state.file}
          folder={state.folder}
        />
      )}
      {state.kind === "delete" && (
        <DeleteFileAlertDialog open onOpenChange={close} file={state.file} />
      )}
    </FileActionsContext.Provider>
  )
}
