import * as React from "react"

import { toast } from "sonner"

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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useBuckets } from "@/hooks/use-buckets"
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

type PreferredBucketProps = WithOpenChange & {
  folder: FolderTreeNode
}

function PreferredBucketForm({
  folder,
  onDone,
}: {
  folder: FolderTreeNode
  onDone: () => void
}) {
  const update = useUpdateFolder()
  const bucketsQuery = useBuckets()
  const buckets = React.useMemo(
    () => bucketsQuery.data ?? [],
    [bucketsQuery.data]
  )

  const [choice, setChoice] = React.useState(() =>
    folder.preferred_bucket_id ?? "inherit"
  )

  const effectivePreferredName = React.useMemo(() => {
    if (folder.effective_preferred_bucket_id == null) return null
    return (
      buckets.find((b) => b.id === folder.effective_preferred_bucket_id)?.name ??
      "an unknown bucket"
    )
  }, [buckets, folder.effective_preferred_bucket_id])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const payload = choice === "inherit" ? null : choice
    try {
      await update.mutateAsync({
        id: folder.id,
        preferred_bucket_id: payload,
      })
      toast.success("Preferred bucket updated")
      onDone()
    } catch {
      // hook toasts the error
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>Preferred bucket</DialogTitle>
        <DialogDescription>
          Optional placement hint for <code>{folder.path || "/"}</code>. Without
          a preference Relic places new uploads in the hottest reachable
          bucket. The preference is honored when the bucket has capacity; the
          maintenance loop can still demote/promote based on access patterns.
        </DialogDescription>
      </DialogHeader>
      <form className="flex flex-col gap-3" onSubmit={submit}>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="preferred-bucket">Preferred bucket</Label>
          <Select
            value={choice}
            onValueChange={setChoice}
            disabled={update.isPending || bucketsQuery.isLoading}
          >
            <SelectTrigger id="preferred-bucket" className="w-full">
              <SelectValue placeholder="Select a bucket" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="inherit">
                {effectivePreferredName == null
                  ? "No preference (inherit)"
                  : `Inherit (${effectivePreferredName})`}
              </SelectItem>
              {buckets.map((bucket) => (
                <SelectItem key={bucket.id} value={bucket.id}>
                  {bucket.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-muted-foreground text-xs">
            "Inherit" walks up to the nearest ancestor with a preference set.
            For a deduplicated blob, the preference is only applied when every
            referencing folder agrees on the same effective bucket.
          </p>
        </div>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={onDone}
            disabled={update.isPending}
          >
            Cancel
          </Button>
          <Button type="submit" disabled={update.isPending}>
            Save
          </Button>
        </DialogFooter>
      </form>
    </>
  )
}

export function PreferredBucketDialog({
  open,
  onOpenChange,
  folder,
}: PreferredBucketProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        {open ? (
          <PreferredBucketForm
            key={`${folder.id}-${folder.preferred_bucket_id ?? "i"}-${folder.effective_preferred_bucket_id ?? ""}`}
            folder={folder}
            onDone={() => onOpenChange(false)}
          />
        ) : null}
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
