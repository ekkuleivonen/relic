import * as React from "react"

import { FileMenuItems } from "@/components/filesystem/file-menu-items"
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuTrigger,
} from "@/components/ui/context-menu"
import type { FileSystemFile, FolderTreeNode } from "@/types/filesystem"

type FileContextMenuProps = {
  file: FileSystemFile
  folder: FolderTreeNode
  children: React.ReactNode
  asChild?: boolean
}

export function FileContextMenu({
  file,
  folder,
  children,
  asChild = true,
}: FileContextMenuProps) {
  return (
    <ContextMenu>
      <ContextMenuTrigger asChild={asChild}>{children}</ContextMenuTrigger>
      <ContextMenuContent className="w-52">
        <FileMenuItems file={file} folder={folder} variant="context" />
      </ContextMenuContent>
    </ContextMenu>
  )
}
