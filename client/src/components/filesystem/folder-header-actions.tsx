import * as React from "react"
import { FolderPlus, MoreHorizontal, Upload } from "lucide-react"

import { useFolderActions } from "@/hooks/use-folder-actions"
import { FolderMenuItems } from "@/components/filesystem/folder-menu-items"
import { Button } from "@/components/ui/button"
import { useFileUpload } from "@/hooks/use-file-upload"
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
  const fileInputRef = React.useRef<HTMLInputElement>(null)
  const uploadFile = useFileUpload()
  const canWrite = can(folder.effective_permissions, PERM.WRITE)

  async function handleSelectedFiles(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.currentTarget.files ?? [])
    event.currentTarget.value = ""

    for (const file of files) {
      try {
        await uploadFile.mutateAsync({ folder_id: folder.id, file })
      } catch {
        // The mutation already surfaces each failed upload through toast.error.
      }
    }
  }

  return (
    <div className="flex items-center gap-2">
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(event) => void handleSelectedFiles(event)}
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => fileInputRef.current?.click()}
        disabled={!canWrite || uploadFile.isPending}
      >
        <Upload />
        Upload files
      </Button>
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
