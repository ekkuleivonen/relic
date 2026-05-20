import * as React from "react"

import { MetaJsonEditor } from "@/components/filesystem/meta-json-editor"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useBulkMoveFiles, useBulkPatchFileMeta } from "@/hooks/use-files"
import { useFolderTree } from "@/hooks/use-filesystem"
import { META_PATCH_HINT, parseMetaPatchJson } from "@/lib/file-meta"
import { canAcceptFiles } from "@/lib/permissions"
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
    if (node.id !== excludeFolderId && canAcceptFiles(node)) {
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
  const [metaJson, setMetaJson] = React.useState("{}")
  const [parseError, setParseError] = React.useState<string | null>(null)

  function handleOpenChange(next: boolean) {
    if (!next) {
      setMetaJson("{}")
      setParseError(null)
    }
    onOpenChange(next)
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const { meta, error } = parseMetaPatchJson(metaJson)
    if (error || !meta) {
      setParseError(error)
      return
    }
    setParseError(null)

    try {
      await bulkPatch.mutateAsync({ file_ids: fileIds, meta })
      handleOpenChange(false)
      onCompleted()
    } catch {
      // hook toasts the error
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Merge metadata into {fileIds.length} files</DialogTitle>
          <DialogDescription>
            Provide a JSON object to deep-merge into each selected file. Omitted
            keys are left unchanged.
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={submit}>
          <MetaJsonEditor
            id="bulk-meta-json"
            value={metaJson}
            onChange={setMetaJson}
            rows={10}
            error={parseError}
            onErrorChange={setParseError}
          />
          <p className="text-xs text-muted-foreground">{META_PATCH_HINT}</p>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
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
