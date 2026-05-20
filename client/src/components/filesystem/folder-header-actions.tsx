import { FolderPlus, MoreHorizontal, Upload } from "lucide-react"

import { useFolderActions } from "@/hooks/use-folder-actions"
import { UploadFilesDialog } from "@/components/filesystem/upload-files-dialog"
import { useUploadWithMetaDialog } from "@/hooks/use-upload-with-meta-dialog"
import { FolderMenuItems } from "@/components/filesystem/folder-menu-items"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { PERM, can, canAcceptFiles } from "@/lib/permissions"
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
  const canEnrich = can(folder.effective_permissions, PERM.ENRICH)
  const acceptsFiles = canAcceptFiles(folder)
  const upload = useUploadWithMetaDialog({
    folderId: folder.id,
    canSetMeta: canEnrich,
    disabled: !acceptsFiles,
  })
  const uploadDisabled = !acceptsFiles

  return (
    <div className="flex items-center gap-2">
      <UploadFilesDialog {...upload.uploadDialogProps} />
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => upload.openUploadDialog()}
              disabled={uploadDisabled}
            >
              <Upload />
              Upload files
            </Button>
          </span>
        </TooltipTrigger>
        {!acceptsFiles && canWrite ? (
          <TooltipContent>Create a subfolder first — files cannot live in root.</TooltipContent>
        ) : canEnrich ? (
          <TooltipContent>
            Add optional metadata before upload, or drop files onto the folder.
          </TooltipContent>
        ) : null}
      </Tooltip>
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
