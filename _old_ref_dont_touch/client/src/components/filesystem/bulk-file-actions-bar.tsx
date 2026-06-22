import * as React from "react"
import { FolderInput, Tags, Trash2 } from "lucide-react"

import {
  BulkMoveFilesDialog,
  BulkPatchMetaDialog,
} from "@/components/filesystem/bulk-file-dialogs"
import { Button } from "@/components/ui/button"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { useBulkDeleteFiles } from "@/hooks/use-files"
import { PERM, can } from "@/lib/permissions"
import type { FolderTreeNode } from "@/types/filesystem"

type BulkFileActionsBarProps = {
  selectedFileIds: string[]
  currentFolder: FolderTreeNode
  onClearSelection: () => void
}

export function BulkFileActionsBar({
  selectedFileIds,
  currentFolder,
  onClearSelection,
}: BulkFileActionsBarProps) {
  const bulkDelete = useBulkDeleteFiles()
  const [confirmOpen, setConfirmOpen] = React.useState(false)
  const [moveOpen, setMoveOpen] = React.useState(false)
  const [metaOpen, setMetaOpen] = React.useState(false)
  const canEnrich = can(currentFolder.effective_permissions, PERM.ENRICH)

  if (selectedFileIds.length === 0) {
    return null
  }

  async function handleDelete() {
    await bulkDelete.mutateAsync(selectedFileIds)
    setConfirmOpen(false)
    onClearSelection()
  }

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-md border bg-muted/40 px-3 py-2">
        <span className="text-sm text-muted-foreground">
          {selectedFileIds.length} file
          {selectedFileIds.length === 1 ? "" : "s"} selected
        </span>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => setMoveOpen(true)}
        >
          <FolderInput className="size-4" />
          Move
        </Button>
        {canEnrich ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setMetaOpen(true)}
          >
            <Tags className="size-4" />
            Edit metadata
          </Button>
        ) : null}
        <Button
          type="button"
          size="sm"
          variant="destructive"
          onClick={() => setConfirmOpen(true)}
        >
          <Trash2 className="size-4" />
          Delete
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onClearSelection}>
          Clear
        </Button>
      </div>

      <BulkMoveFilesDialog
        open={moveOpen}
        onOpenChange={setMoveOpen}
        fileIds={selectedFileIds}
        sourceFolder={currentFolder}
        onCompleted={onClearSelection}
      />

      <BulkPatchMetaDialog
        open={metaOpen}
        onOpenChange={setMetaOpen}
        fileIds={selectedFileIds}
        onCompleted={onClearSelection}
      />

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete selected files?</AlertDialogTitle>
            <AlertDialogDescription>
              This removes {selectedFileIds.length} file record
              {selectedFileIds.length === 1 ? "" : "s"} from the filesystem. Blob
              bytes are purged when refcount reaches zero.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={bulkDelete.isPending}
              onClick={(event) => {
                event.preventDefault()
                void handleDelete()
              }}
            >
              {bulkDelete.isPending ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
