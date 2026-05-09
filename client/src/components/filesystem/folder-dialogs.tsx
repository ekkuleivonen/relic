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
import {
  useCreateFolder,
  useDeleteFolder,
  useDuplicateFolder,
  useUpdateFolder,
} from "@/hooks/use-folders"
import type { FolderTreeNode } from "@/types/filesystem"

type WithOpenChange = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

type CreateProps = WithOpenChange & {
  parent: FolderTreeNode
}

export function CreateFolderDialog({ open, onOpenChange, parent }: CreateProps) {
  const [name, setName] = React.useState("")
  const create = useCreateFolder()

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      return
    }
    try {
      await create.mutateAsync({ parent_id: parent.id, name: trimmed })
      onOpenChange(false)
    } catch {
      // toast already handled in the hook
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New folder</DialogTitle>
          <DialogDescription>
            Create a folder under <code>{parent.path || "/"}</code>.
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={submit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="new-folder-name">Name</Label>
            <Input
              id="new-folder-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="my-folder"
              autoFocus
              disabled={create.isPending}
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={create.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending || !name.trim()}>
              Create
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

type RenameProps = WithOpenChange & {
  folder: FolderTreeNode
}

export function RenameFolderDialog({ open, onOpenChange, folder }: RenameProps) {
  const [name, setName] = React.useState(folder.name)
  const update = useUpdateFolder()

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed || trimmed === folder.name) {
      onOpenChange(false)
      return
    }
    try {
      await update.mutateAsync({ id: folder.id, name: trimmed })
      onOpenChange(false)
    } catch {
      // hook toasts the error
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rename folder</DialogTitle>
          <DialogDescription>
            Currently <code>{folder.path}</code>.
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={submit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rename-folder-name">Name</Label>
            <Input
              id="rename-folder-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoFocus
              disabled={update.isPending}
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={update.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={update.isPending || !name.trim()}>
              Rename
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

type DuplicateProps = WithOpenChange & {
  folder: FolderTreeNode
}

export function DuplicateFolderDialog({
  open,
  onOpenChange,
  folder,
}: DuplicateProps) {
  const [name, setName] = React.useState(`${folder.name} copy`)
  const duplicate = useDuplicateFolder()
  const destinationParentId = folder.parent_id

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed || destinationParentId === null) {
      return
    }
    try {
      await duplicate.mutateAsync({
        id: folder.id,
        destination_parent_id: destinationParentId,
        name: trimmed,
        recursive: true,
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
          <DialogTitle>Duplicate folder</DialogTitle>
          <DialogDescription>
            Create a copy of <code>{folder.path}</code> in the same location.
            All subfolders and files are copied.
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={submit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="duplicate-folder-name">New name</Label>
            <Input
              id="duplicate-folder-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoFocus
              disabled={duplicate.isPending}
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={duplicate.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={duplicate.isPending || !name.trim()}
            >
              Duplicate
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

type DeleteProps = WithOpenChange & {
  folder: FolderTreeNode
  onDeleted?: () => void
}

export function DeleteFolderDialog({
  open,
  onOpenChange,
  folder,
  onDeleted,
}: DeleteProps) {
  const remove = useDeleteFolder()
  const subfolderCount = folder.children.length
  const isNotEmpty = subfolderCount > 0
  const description = isNotEmpty
    ? `This will permanently delete '${folder.name}' and ${subfolderCount} ${subfolderCount === 1 ? "subfolder" : "subfolders"} (plus all files inside).`
    : `This will permanently delete '${folder.name}'.`

  async function confirm() {
    try {
      await remove.mutateAsync({ id: folder.id, recursive: true })
      onOpenChange(false)
      onDeleted?.()
    } catch {
      // hook toasts the error
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete folder?</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
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
