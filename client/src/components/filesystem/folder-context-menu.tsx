import * as React from "react"

import { FolderMenuItems } from "@/components/filesystem/folder-menu-items"
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuTrigger,
} from "@/components/ui/context-menu"
import type { FolderTreeNode } from "@/types/filesystem"

type FolderContextMenuProps = {
  folder: FolderTreeNode
  children: React.ReactNode
  asChild?: boolean
  onAfterDelete?: () => void
}

export function FolderContextMenu({
  folder,
  children,
  asChild = true,
  onAfterDelete,
}: FolderContextMenuProps) {
  return (
    <ContextMenu>
      <ContextMenuTrigger asChild={asChild}>{children}</ContextMenuTrigger>
      <ContextMenuContent className="w-52">
        <FolderMenuItems
          folder={folder}
          variant="context"
          onAfterDelete={onAfterDelete}
        />
      </ContextMenuContent>
    </ContextMenu>
  )
}
