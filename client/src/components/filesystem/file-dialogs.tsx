import * as React from "react"

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
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useFolderTree } from "@/hooks/use-filesystem"
import {
  useCopyFile,
  useDeleteFile,
  useMoveFile,
  useRenameFile,
} from "@/hooks/use-files"
import { PERM, can } from "@/lib/permissions"
import { cn } from "@/lib/utils"
import type { FileSystemFile, FolderTreeNode } from "@/types/filesystem"

type WithOpenChange = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

type RenameProps = WithOpenChange & {
  file: FileSystemFile
}

export function RenameFileDialog({ open, onOpenChange, file }: RenameProps) {
  const [name, setName] = React.useState(file.name)
  const rename = useRenameFile()

  React.useEffect(() => {
    if (open) {
      setName(file.name)
    }
  }, [open, file.name])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed || trimmed === file.name) {
      onOpenChange(false)
      return
    }
    try {
      await rename.mutateAsync({ file_id: file.id, name: trimmed })
      onOpenChange(false)
    } catch {
      // hook toasts the error
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rename file</DialogTitle>
          <DialogDescription>
            Currently <code>{file.name}</code>.
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={submit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rename-file-name">Name</Label>
            <Input
              id="rename-file-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoFocus
              disabled={rename.isPending}
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={rename.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={rename.isPending || !name.trim()}>
              Rename
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

type DuplicateProps = WithOpenChange & {
  file: FileSystemFile
  folder: FolderTreeNode
}

export function DuplicateFileDialog({
  open,
  onOpenChange,
  file,
  folder,
}: DuplicateProps) {
  const [name, setName] = React.useState(() => suggestCopyName(file.name))
  const copy = useCopyFile()

  React.useEffect(() => {
    if (open) {
      setName(suggestCopyName(file.name))
    }
  }, [open, file.name])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      return
    }
    try {
      await copy.mutateAsync({
        source_file_id: file.id,
        destination_folder_id: folder.id,
        name: trimmed,
        metadata_directive: "COPY",
      })
      onOpenChange(false)
    } catch {
      // hook toasts the error
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Duplicate file</DialogTitle>
          <DialogDescription>
            Create a copy of <code>{file.name}</code> in this folder.
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={submit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="duplicate-file-name">New name</Label>
            <Input
              id="duplicate-file-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoFocus
              disabled={copy.isPending}
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={copy.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={copy.isPending || !name.trim()}>
              Duplicate
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

type MoveProps = WithOpenChange & {
  file: FileSystemFile
  folder: FolderTreeNode
}

export function MoveFileDialog({
  open,
  onOpenChange,
  file,
  folder,
}: MoveProps) {
  const tree = useFolderTree()
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const move = useMoveFile()

  React.useEffect(() => {
    if (open) {
      setSelectedId(null)
    }
  }, [open])

  const candidates = React.useMemo(() => {
    if (!tree.data) return []
    return collectWritableFolders(tree.data, folder.id)
  }, [tree.data, folder.id])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!selectedId) return
    try {
      await move.mutateAsync({
        file_id: file.id,
        destination_folder_id: selectedId,
      })
      onOpenChange(false)
    } catch {
      // hook toasts the error
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Move file</DialogTitle>
          <DialogDescription>
            Pick a destination folder for <code>{file.name}</code>.
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
              disabled={move.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={move.isPending || selectedId === null}
            >
              Move
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

type DeleteProps = WithOpenChange & {
  file: FileSystemFile
}

export function DeleteFileAlertDialog({ open, onOpenChange, file }: DeleteProps) {
  const remove = useDeleteFile()

  async function confirm() {
    try {
      await remove.mutateAsync({ file_id: file.id, filename: file.name })
      onOpenChange(false)
    } catch {
      // hook toasts the error
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete file?</AlertDialogTitle>
          <AlertDialogDescription>
            This will permanently delete '{file.name}'.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={remove.isPending}>
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            onClick={(event) => {
              event.preventDefault()
              void confirm()
            }}
            disabled={remove.isPending}
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function collectWritableFolders(
  root: FolderTreeNode,
  excludeId: string
): FolderTreeNode[] {
  const out: FolderTreeNode[] = []
  const walk = (node: FolderTreeNode) => {
    const isRoot = node.parent_id === null
    if (
      !isRoot &&
      node.id !== excludeId &&
      can(node.effective_permissions, PERM.WRITE)
    ) {
      out.push(node)
    }
    for (const child of node.children) walk(child)
  }
  walk(root)
  out.sort((a, b) => a.path.localeCompare(b.path))
  return out
}

function suggestCopyName(name: string): string {
  const dot = name.lastIndexOf(".")
  if (dot <= 0) {
    return `${name} copy`
  }
  return `${name.slice(0, dot)} copy${name.slice(dot)}`
}
