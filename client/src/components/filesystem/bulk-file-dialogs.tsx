import * as React from "react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useBulkMoveFiles, useBulkPatchFileMeta } from "@/hooks/use-files"
import { useFolderTree } from "@/hooks/use-filesystem"
import { PERM, can } from "@/lib/permissions"
import { cn } from "@/lib/utils"
import type { FolderTreeNode } from "@/types/filesystem"

type BulkMoveFilesDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  fileIds: string[]
  sourceFolder: FolderTreeNode
  onCompleted: () => void
}

export function BulkMoveFilesDialog({
  open,
  onOpenChange,
  fileIds,
  sourceFolder,
  onCompleted,
}: BulkMoveFilesDialogProps) {
  const tree = useFolderTree()
  const bulkMove = useBulkMoveFiles()
  const [selectedId, setSelectedId] = React.useState<string | null>(null)

  const candidates = React.useMemo(() => {
    if (!tree.data) return []
    return collectWritableFolders(tree.data, sourceFolder.id)
  }, [tree.data, sourceFolder.id])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!selectedId) return
    try {
      await bulkMove.mutateAsync({
        file_ids: fileIds,
        destination_folder_id: selectedId,
      })
      onOpenChange(false)
      onCompleted()
    } catch {
      // hook toasts the error
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Move {fileIds.length} files</DialogTitle>
          <DialogDescription>
            Pick a destination folder for the selected files.
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={submit}>
          <div className="max-h-72 overflow-auto rounded-md border">
            {candidates.length === 0 ? (
              <div className="p-4 text-xs text-muted-foreground">
                No folders available — you need write access to a folder other
                than the current one.
              </div>
            ) : (
              <ul className="divide-y">
                {candidates.map((candidate) => (
                  <li key={candidate.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(candidate.id)}
                      className={cn(
                        "flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-muted",
                        selectedId === candidate.id &&
                          "bg-primary/10 text-foreground"
                      )}
                    >
                      <span className="font-medium">{candidate.path}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={bulkMove.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={bulkMove.isPending || selectedId === null}
            >
              Move
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function collectWritableFolders(
  root: FolderTreeNode,
  excludeFolderId: string
): FolderTreeNode[] {
  const out: FolderTreeNode[] = []

  function walk(node: FolderTreeNode) {
    if (node.id !== excludeFolderId && can(node.effective_permissions, PERM.WRITE)) {
      out.push(node)
    }
    for (const child of node.children) {
      walk(child)
    }
  }

  walk(root)
  return out.sort((a, b) => a.path.localeCompare(b.path))
}

type BulkPatchMetaDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  fileIds: string[]
  onCompleted: () => void
}

export function BulkPatchMetaDialog({
  open,
  onOpenChange,
  fileIds,
  onCompleted,
}: BulkPatchMetaDialogProps) {
  const bulkPatch = useBulkPatchFileMeta()
  const [metaJson, setMetaJson] = React.useState('{\n  "tags": []\n}')
  const [parseError, setParseError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!open) {
      setMetaJson('{\n  "tags": []\n}')
      setParseError(null)
    }
  }, [open])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    let meta: Record<string, unknown>
    try {
      meta = JSON.parse(metaJson) as Record<string, unknown>
      if (meta === null || Array.isArray(meta) || typeof meta !== "object") {
        throw new Error("Metadata must be a JSON object")
      }
      setParseError(null)
    } catch (error) {
      setParseError(
        error instanceof Error ? error.message : "Invalid JSON metadata"
      )
      return
    }

    try {
      await bulkPatch.mutateAsync({ file_ids: fileIds, meta })
      onOpenChange(false)
      onCompleted()
    } catch {
      // hook toasts the error
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit metadata for {fileIds.length} files</DialogTitle>
          <DialogDescription>
            Provide a JSON object to deep-merge into each selected file&apos;s
            metadata. Omitted keys are left unchanged.
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={submit}>
          <div className="grid gap-2">
            <Label htmlFor="bulk-meta-json">Metadata patch</Label>
            <Textarea
              id="bulk-meta-json"
              value={metaJson}
              onChange={(event) => {
                setMetaJson(event.target.value)
                setParseError(null)
              }}
              rows={10}
              className="font-mono text-xs"
              spellCheck={false}
            />
            {parseError ? (
              <p className="text-xs text-destructive">{parseError}</p>
            ) : null}
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={bulkPatch.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={bulkPatch.isPending}>
              {bulkPatch.isPending ? "Saving..." : "Apply"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
