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
import {
  useCreateFolder,
  useDeleteFolder,
  useDuplicateFolder,
  useUpdateFolder,
} from "@/hooks/use-folders"
import { bucketTiers } from "@/types/buckets"
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

type StoragePolicyProps = WithOpenChange & {
  folder: FolderTreeNode
}

function StoragePolicyForm({
  folder,
  onDone,
}: {
  folder: FolderTreeNode
  onDone: () => void
}) {
  const update = useUpdateFolder()
  const isRoot = folder.parent_id === null

  const [minTierChoice, setMinTierChoice] = React.useState(() => {
    if (isRoot) {
      return String(
        folder.min_tier ?? folder.effective_min_tier ?? 1
      )
    }
    return folder.min_tier != null ? String(folder.min_tier) : "inherit"
  })
  const [cooldownInput, setCooldownInput] = React.useState(() =>
    folder.cooldown_days != null ? String(folder.cooldown_days) : ""
  )

  const effectiveTierLabel =
    bucketTiers.find((t) => t.value === folder.effective_min_tier)?.label ??
    "Hot"
  const effectiveCooldown =
    folder.effective_cooldown_days != null
      ? `${folder.effective_cooldown_days} day${folder.effective_cooldown_days === 1 ? "" : "s"}`
      : "none"

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const trimmed = cooldownInput.trim()
    let cooldown: number | null
    if (trimmed === "") {
      cooldown = null
    } else {
      const parsed = Number.parseInt(trimmed, 10)
      if (!Number.isFinite(parsed) || parsed < 1) {
        return
      }
      cooldown = parsed
    }

    let minTierPayload: number | null
    if (isRoot) {
      const parsed = Number.parseInt(minTierChoice, 10)
      if (!Number.isFinite(parsed) || parsed < 1 || parsed > 4) {
        return
      }
      minTierPayload = parsed
    } else {
      minTierPayload =
        minTierChoice === "inherit" ? null : Number.parseInt(minTierChoice, 10)
    }

    try {
      await update.mutateAsync({
        id: folder.id,
        min_tier: minTierPayload,
        cooldown_days: cooldown,
      })
      toast.success("Storage policy updated")
      onDone()
    } catch {
      // hook toasts the error
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>Folder storage policy</DialogTitle>
        <DialogDescription>
          Minimum tier and optional cooldown for <code>{folder.path || "/"}</code>.
          Non-root folders can inherit from parents; overrides apply to this folder
          and descendants until changed again.
        </DialogDescription>
      </DialogHeader>
      <form className="flex flex-col gap-3" onSubmit={submit}>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="storage-min-tier">Minimum tier</Label>
          <Select
            value={minTierChoice}
            onValueChange={setMinTierChoice}
            disabled={update.isPending}
          >
            <SelectTrigger id="storage-min-tier" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {!isRoot ? (
                <SelectItem value="inherit">
                  Inherit ({effectiveTierLabel})
                </SelectItem>
              ) : null}
              {bucketTiers.map((tier) => (
                <SelectItem key={tier.value} value={String(tier.value)}>
                  {tier.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="storage-cooldown">Cooldown (days)</Label>
          <Input
            id="storage-cooldown"
            type="text"
            inputMode="numeric"
            placeholder="Leave empty to inherit"
            value={cooldownInput}
            onChange={(event) => setCooldownInput(event.target.value)}
            disabled={update.isPending}
          />
          <p className="text-muted-foreground text-xs">
            Effective cooldown today: {effectiveCooldown}. Empty field inherits
            from a parent when set; otherwise none.
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

export function StoragePolicyDialog({
  open,
  onOpenChange,
  folder,
}: StoragePolicyProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        {open ? (
          <StoragePolicyForm
            key={`${folder.id}-${folder.min_tier ?? "i"}-${folder.cooldown_days ?? ""}-${folder.effective_min_tier ?? ""}-${folder.effective_cooldown_days ?? ""}`}
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
