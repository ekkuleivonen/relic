import { FolderPlus, MoreHorizontal } from "lucide-react"

import { useFolderActions } from "@/hooks/use-folder-actions"
import { FolderMenuItems } from "@/components/filesystem/folder-menu-items"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { PERM, can } from "@/lib/permissions"
import type { FolderTreeNode } from "@/types/filesystem"

type FolderHeaderActionsProps = {
  folder: FolderTreeNode
  onAfterDelete?: () => void
}

export function FolderHeaderActions({
  folder,
  onAfterDelete,
}: FolderHeaderActionsProps) {
  const actions = useFolderActions()
  const canWrite = can(folder.effective_permissions, PERM.WRITE)

  return (
    <div className="flex items-center gap-2">
      <Button
        type="button"
        variant="default"
        size="sm"
        onClick={() => actions.openCreate(folder)}
        disabled={!canWrite}
      >
        <FolderPlus />
        New folder
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="icon-sm"
            aria-label="Folder actions"
          >
            <MoreHorizontal />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-52">
          <FolderMenuItems
            folder={folder}
            variant="dropdown"
            onAfterDelete={onAfterDelete}
          />
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
