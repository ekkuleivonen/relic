import * as React from "react"

import type { UploadFilesDialogProps } from "@/components/filesystem/upload-files-dialog"
import { useNativeFileDrop } from "@/hooks/use-native-file-drop"

type UseUploadWithMetaDialogArgs = {
  folderId: string
  canSetMeta: boolean
  disabled?: boolean
}

export function useUploadWithMetaDialog({
  folderId,
  canSetMeta,
  disabled = false,
}: UseUploadWithMetaDialogArgs) {
  const [open, setOpen] = React.useState(false)
  const [pendingFiles, setPendingFiles] = React.useState<File[]>([])

  function openUploadDialog(files: File[] = []) {
    setPendingFiles(files)
    setOpen(true)
  }

  function handleOpenChange(next: boolean) {
    setOpen(next)
    if (!next) {
      setPendingFiles([])
    }
  }

  const drop = useNativeFileDrop({
    folderId,
    disabled,
    onFilesSelected: canSetMeta ? openUploadDialog : undefined,
  })

  const uploadDialogProps: UploadFilesDialogProps = {
    open,
    onOpenChange: handleOpenChange,
    folderId,
    canSetMeta,
    initialFiles: pendingFiles,
  }

  return {
    openUploadDialog,
    dropHandlers: drop.handlers,
    isOver: drop.isOver,
    uploadDialogProps,
  }
}
