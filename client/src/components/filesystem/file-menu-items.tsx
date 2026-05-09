import { Copy, Download, FolderInput, Pencil, Trash2 } from "lucide-react"

import { useFileActions } from "@/hooks/use-file-actions"
import {
  ContextMenuItem,
  ContextMenuSeparator,
} from "@/components/ui/context-menu"
import {
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"
import { PERM, can } from "@/lib/permissions"
import type { FileSystemFile, FolderTreeNode } from "@/types/filesystem"

export type FileMenuVariant = "context" | "dropdown"

type FileMenuItemsProps = {
  file: FileSystemFile
  folder: FolderTreeNode
  variant: FileMenuVariant
}

export function FileMenuItems({ file, folder, variant }: FileMenuItemsProps) {
  const actions = useFileActions()
  const canRead = can(folder.effective_permissions, PERM.READ)
  const canWrite = can(folder.effective_permissions, PERM.WRITE)
  const canDelete = can(folder.effective_permissions, PERM.DELETE)

  const Item = variant === "context" ? ContextMenuItem : DropdownMenuItem
  const Separator =
    variant === "context" ? ContextMenuSeparator : DropdownMenuSeparator

  return (
    <>
      <Item
        disabled={!canRead}
        onSelect={(event) => {
          event.preventDefault()
          actions.download(file)
        }}
      >
        <Download />
        <span>Download</span>
      </Item>
      <Separator />
      <Item
        disabled={!canWrite}
        onSelect={(event) => {
          event.preventDefault()
          actions.openRename(file)
        }}
      >
        <Pencil />
        <span>Rename…</span>
      </Item>
      <Item
        disabled={!canWrite}
        onSelect={(event) => {
          event.preventDefault()
          actions.openDuplicate(file, folder)
        }}
      >
        <Copy />
        <span>Duplicate…</span>
      </Item>
      <Item
        disabled={!canDelete}
        onSelect={(event) => {
          event.preventDefault()
          actions.openMove(file, folder)
        }}
      >
        <FolderInput />
        <span>Move to…</span>
      </Item>
      <Separator />
      <Item
        variant="destructive"
        disabled={!canDelete}
        onSelect={(event) => {
          event.preventDefault()
          actions.openDelete(file)
        }}
      >
        <Trash2 />
        <span>Delete</span>
      </Item>
    </>
  )
}
