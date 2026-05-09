import { Copy, FolderPlus, Pencil, Trash2 } from "lucide-react"

import { useFolderActions } from "@/hooks/use-folder-actions"
import {
  ContextMenuItem,
  ContextMenuSeparator,
} from "@/components/ui/context-menu"
import {
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"
import { PERM, can } from "@/lib/permissions"
import type { FolderTreeNode } from "@/types/filesystem"

export type FolderMenuVariant = "context" | "dropdown"

type FolderMenuItemsProps = {
  folder: FolderTreeNode
  variant: FolderMenuVariant
  onAfterDelete?: () => void
}

export function FolderMenuItems({
  folder,
  variant,
  onAfterDelete,
}: FolderMenuItemsProps) {
  const actions = useFolderActions()
  const isRoot = folder.parent_id === null
  const canWrite = can(folder.effective_permissions, PERM.WRITE)
  const canDelete = can(folder.effective_permissions, PERM.DELETE)

  const Item = variant === "context" ? ContextMenuItem : DropdownMenuItem
  const Separator =
    variant === "context" ? ContextMenuSeparator : DropdownMenuSeparator

  return (
    <>
      <Item
        disabled={!canWrite}
        onSelect={(event) => {
          event.preventDefault()
          actions.openCreate(folder)
        }}
      >
        <FolderPlus />
        <span>New folder here</span>
      </Item>
      {!isRoot && <Separator />}
      {!isRoot && (
        <>
          <Item
            disabled={!canWrite}
            onSelect={(event) => {
              event.preventDefault()
              actions.openRename(folder)
            }}
          >
            <Pencil />
            <span>Rename…</span>
          </Item>
          <Item
            disabled={!canWrite}
            onSelect={(event) => {
              event.preventDefault()
              actions.openDuplicate(folder)
            }}
          >
            <Copy />
            <span>Duplicate…</span>
          </Item>
          <Separator />
          <Item
            variant="destructive"
            disabled={!canDelete}
            onSelect={(event) => {
              event.preventDefault()
              actions.openDelete(folder, onAfterDelete)
            }}
          >
            <Trash2 />
            <span>Delete</span>
          </Item>
        </>
      )}
    </>
  )
}
